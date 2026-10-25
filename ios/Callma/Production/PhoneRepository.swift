import Foundation

protocol PhoneRepository {
    func load() throws -> PhoneSnapshot
    func save(_ snapshot: PhoneSnapshot) throws
}

enum AppStoragePaths {
    /// Reuse an existing file under either app name without moving or discarding it.
    static func file(_ name: String, base: URL = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]) -> URL {
        let current = base.appendingPathComponent("Callma", isDirectory: true).appendingPathComponent(name)
        let legacy = base.appendingPathComponent("Callshield", isDirectory: true).appendingPathComponent(name)
        if !FileManager.default.fileExists(atPath: current.path), FileManager.default.fileExists(atPath: legacy.path) {
            return legacy
        }
        return current
    }
}

struct LocalPhoneRepository: PhoneRepository {
    let url: URL
    init(url: URL? = nil) {
        self.url = url ?? AppStoragePaths.file("phone-v1.json")
    }
    func load() throws -> PhoneSnapshot {
        guard FileManager.default.fileExists(atPath: url.path) else { return PhoneSnapshot() }
        return try JSONDecoder().decode(PhoneSnapshot.self, from: Data(contentsOf: url))
    }
    func save(_ snapshot: PhoneSnapshot) throws {
        try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
        var bounded = snapshot
        bounded.history = Array(snapshot.history.prefix(1000))
        var directory = url.deletingLastPathComponent()
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        let data = try JSONEncoder().encode(bounded)
        try data.write(to: url, options: [.atomic, .completeFileProtectionUntilFirstUserAuthentication])
    }
}
