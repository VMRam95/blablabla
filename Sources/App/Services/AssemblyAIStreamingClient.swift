import Foundation

struct AssemblyAIMessage: Decodable {
    let type: String
    let transcript: String?
    let endOfTurn: Bool?
    let audioDurationSeconds: Double?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case type
        case transcript
        case endOfTurn = "end_of_turn"
        case audioDurationSeconds = "audio_duration_seconds"
        case error
    }
}

final class AssemblyAIStreamingClient {
    var onEvent: ((AssemblyAIMessage) -> Void)?
    var onFailure: ((String) -> Void)?

    private let decoder = JSONDecoder()
    private var session: URLSession?
    private var socketTask: URLSessionWebSocketTask?
    private let sendQueue = DispatchQueue(label: "AssemblyAIStreamingClient.send")
    private var isStopping = false

    func start(apiKey: String) async throws {
        isStopping = false
        // A previous session may still be draining while the new token loads.
        // Its delayed cleanup retains its own handles, not these properties.
        socketTask = nil
        session = nil
        let token = try await fetchTemporaryToken(apiKey: apiKey)
        try await openSocket(token: token)
    }

    func sendAudio(_ data: Data) {
        guard let socketTask else { return }
        sendQueue.async { [weak self] in
            guard let self, self.socketTask === socketTask, !self.isStopping else { return }
            socketTask.send(.data(data)) { [weak self] error in
                if let error, let self, self.socketTask === socketTask, !self.isStopping {
                    self.onFailure?(error.localizedDescription)
                }
            }
        }
    }

    func stop() {
        guard !isStopping else { return }
        isStopping = true
        let socketTask = self.socketTask
        let session = self.session

        let payload = ["type": "Terminate"]
        if let data = try? JSONSerialization.data(withJSONObject: payload),
           let text = String(data: data, encoding: .utf8),
           let socketTask {
            socketTask.send(.string(text)) { [weak self] error in
                if let error, let self, self.socketTask === socketTask {
                    self.onFailure?(error.localizedDescription)
                }
            }
        }

        DispatchQueue.global().asyncAfter(deadline: .now() + 1.2) { [weak self] in
            socketTask?.cancel(with: .goingAway, reason: nil)
            session?.invalidateAndCancel()
            guard let self, self.socketTask === socketTask else { return }
            self.socketTask = nil
            self.session = nil
        }
    }

    private func fetchTemporaryToken(apiKey: String) async throws -> String {
        var components = URLComponents(string: "https://streaming.assemblyai.com/v3/token")!
        components.queryItems = [URLQueryItem(name: "expires_in_seconds", value: "300")]

        var request = URLRequest(url: components.url!)
        request.httpMethod = "GET"
        request.setValue(apiKey, forHTTPHeaderField: "Authorization")

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw AssemblyAIError.invalidResponse
        }

        guard (200..<300).contains(httpResponse.statusCode) else {
            let body = String(data: data, encoding: .utf8) ?? "unknown error"
            throw AssemblyAIError.tokenRequestFailed(body)
        }

        let tokenPayload = try JSONDecoder().decode(TokenPayload.self, from: data)
        return tokenPayload.token
    }

    private func openSocket(token: String) async throws {
        var components = URLComponents(string: "wss://streaming.assemblyai.com/v3/ws")!
        components.queryItems = [
            URLQueryItem(name: "sample_rate", value: "16000"),
            URLQueryItem(name: "encoding", value: "pcm_s16le"),
            URLQueryItem(name: "speech_model", value: "u3-rt-pro"),
            URLQueryItem(name: "token", value: token)
        ]

        let session = URLSession(configuration: .default)
        let socketTask = session.webSocketTask(with: components.url!)
        self.session = session
        self.socketTask = socketTask
        socketTask.resume()
        receiveNextMessage()
    }

    private func receiveNextMessage() {
        guard let socketTask else { return }
        socketTask.receive { [weak self] result in
            guard let self, self.socketTask === socketTask else { return }

            switch result {
            case .failure(let error):
                if !self.isStopping {
                    self.onFailure?(error.localizedDescription)
                }
            case .success(let message):
                switch message {
                case .string(let text):
                    self.handleRawMessage(text, from: socketTask)
                case .data(let data):
                    self.handleRawMessage(String(decoding: data, as: UTF8.self), from: socketTask)
                @unknown default:
                    break
                }

                if !self.isStopping || self.socketTask != nil {
                    self.receiveNextMessage()
                }
            }
        }
    }

    private func handleRawMessage(_ rawText: String, from socketTask: URLSessionWebSocketTask) {
        guard let data = rawText.data(using: .utf8) else { return }

        do {
            let decoded = try decoder.decode(AssemblyAIMessage.self, from: data)
            DispatchQueue.main.async { [weak self] in
                guard let self, self.socketTask === socketTask else { return }
                self.onEvent?(decoded)
            }
        } catch {
            onFailure?("Could not decode AssemblyAI message: \(error.localizedDescription)")
        }
    }
}

private struct TokenPayload: Decodable {
    let token: String
}

enum AssemblyAIError: LocalizedError {
    case invalidResponse
    case tokenRequestFailed(String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "AssemblyAI returned an invalid response while fetching the temporary token."
        case .tokenRequestFailed(let body):
            return "AssemblyAI token request failed: \(body)"
        }
    }
}
