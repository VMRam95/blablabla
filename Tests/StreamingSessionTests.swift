
// Appended to AssemblyAIStreamingClient.swift by run-streaming-tests.sh.
// Transport doubles shadow Foundation's types in this test compilation only.
// The production client is compiled unchanged; no network or microphone is used.
private final class URLSessionWebSocketTask {
    enum Message { case string(String), data(Data) }
    enum CloseCode { case goingAway }
    var receiveCompletion: ((Result<Message, Error>) -> Void)?
    var sendCompletions: [(Error?) -> Void] = []
    var messages: [Message] = []
    var cancelCount = 0

    func receive(completionHandler: @escaping (Result<Message, Error>) -> Void) {
        receiveCompletion = completionHandler
    }

    func send(_ message: Message, completionHandler: @escaping (Error?) -> Void) {
        messages.append(message)
        sendCompletions.append(completionHandler)
    }

    func cancel(with closeCode: CloseCode, reason: Data?) {
        cancelCount += 1
    }

    func resume() {}
}

private typealias ControlledSocket = URLSessionWebSocketTask

private final class URLSession {
    static let shared = URLSession()
    init(configuration: URLSessionConfiguration = .ephemeral) {}
    func webSocketTask(with url: URL) -> URLSessionWebSocketTask { ControlledSocket() }
    func invalidateAndCancel() {}
    func data(for request: URLRequest) async throws -> (Data, URLResponse) {
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!
        return (Data(#"{"token":"test-token"}"#.utf8), response)
    }
}

private extension AssemblyAIStreamingClient {
    func installTestConnection(_ socket: ControlledSocket) {
        session = URLSession(configuration: .ephemeral)
        socketTask = socket
        isStopping = false
    }

    func hasTestConnection(_ socket: ControlledSocket) -> Bool {
        socketTask === socket
    }

    func listenForTest() { receiveNextMessage() }
    func suspendAudioForTest() { sendQueue.suspend() }
    func resumeAudioForTest() { sendQueue.resume() }
    func flushAudioForTest() { sendQueue.sync {} }
}

private var failures = 0
private var checks = 0
private func check(_ condition: @autoclosure () -> Bool, _ name: String) {
    checks += 1
    if condition() {
        print("PASS: \(name)")
    } else {
        failures += 1
        print("FAIL: \(name)")
    }
}

private func waitForCallbacks(_ seconds: TimeInterval = 0.05) {
    RunLoop.current.run(until: Date().addingTimeInterval(seconds))
}

private let socketError = NSError(domain: NSPOSIXErrorDomain, code: 57)

// The old delayed close must never cancel or clear its replacement.
do {
    let client = AssemblyAIStreamingClient()
    let old = ControlledSocket()
    let replacement = ControlledSocket()
    client.installTestConnection(old)
    client.stop()
    client.installTestConnection(replacement)
    waitForCallbacks(1.4)
    check(old.cancelCount == 1, "the old socket is closed")
    check(replacement.cancelCount == 0, "the replacement socket stays open")
    check(client.hasTestConnection(replacement), "delayed cleanup preserves replacement state")
    client.stop()
}

// Final Turn/Termination messages must still arrive while a session drains.
do {
    let client = AssemblyAIStreamingClient()
    let socket = ControlledSocket()
    var events: [String] = []
    client.onEvent = { events.append($0.type) }
    client.installTestConnection(socket)
    client.listenForTest()
    client.stop()
    socket.receiveCompletion?(.success(.string(#"{"type":"Turn","transcript":"final words","end_of_turn":true}"#)))
    socket.receiveCompletion?(.success(.string(#"{"type":"Termination"}"#)))
    waitForCallbacks()
    check(events == ["Turn", "Termination"], "stopping preserves final transcript events")
}

// Old receive, audio-send and Terminate errors cannot fail a newer session.
do {
    let client = AssemblyAIStreamingClient()
    let old = ControlledSocket()
    let replacement = ControlledSocket()
    var errors = 0
    client.onFailure = { _ in errors += 1 }
    client.installTestConnection(old)
    client.listenForTest()
    client.sendAudio(Data([0, 0]))
    client.flushAudioForTest()
    client.stop()
    client.installTestConnection(replacement)
    old.receiveCompletion?(.failure(socketError))
    old.sendCompletions.forEach { $0(socketError) }
    waitForCallbacks()
    check(errors == 0, "stale connection errors are ignored")
    client.listenForTest()
    replacement.receiveCompletion?(.failure(socketError))
    check(errors == 1, "active connection errors still reach the app")
    client.stop()
}

// A decoded event queued on the main thread can also outlive its session.
do {
    let client = AssemblyAIStreamingClient()
    let old = ControlledSocket()
    let replacement = ControlledSocket()
    var events: [String] = []
    client.onEvent = { events.append($0.type) }
    client.installTestConnection(old)
    client.listenForTest()
    old.receiveCompletion?(.success(.string(#"{"type":"Turn","transcript":"old words"}"#)))
    client.stop()
    client.installTestConnection(replacement)
    waitForCallbacks()
    check(events.isEmpty, "queued old transcript events are ignored")
    client.listenForTest()
    replacement.receiveCompletion?(.success(.string(#"{"type":"Begin"}"#)))
    waitForCallbacks()
    check(events == ["Begin"], "active transcript events still reach the app")
    client.stop()
}

// Queued PCM belongs to the session that captured it, not the next session.
do {
    let client = AssemblyAIStreamingClient()
    let old = ControlledSocket()
    let replacement = ControlledSocket()
    client.installTestConnection(old)
    client.suspendAudioForTest()
    client.sendAudio(Data([0, 0]))
    client.stop()
    client.installTestConnection(replacement)
    client.resumeAudioForTest()
    client.flushAudioForTest()
    check(replacement.messages.isEmpty, "queued old audio is not sent to the replacement")
    client.stop()
}

do {
    let client = AssemblyAIStreamingClient()
    let socket = ControlledSocket()
    client.installTestConnection(socket)
    client.stop()
    client.stop()
    waitForCallbacks(1.4)
    check(socket.cancelCount == 1, "repeated stop closes the socket only once")
    check(!client.hasTestConnection(socket), "stop without restart clears connection state")
}

do {
    let socket = ControlledSocket()
    var client: AssemblyAIStreamingClient? = AssemblyAIStreamingClient()
    client?.installTestConnection(socket)
    client?.stop()
    client = nil
    waitForCallbacks(1.4)
    check(socket.cancelCount == 1, "scheduled cleanup survives client deallocation")
}

print("\(checks - failures)/\(checks) checks passed; \(failures) failed")
exit(failures == 0 ? 0 : 1)
