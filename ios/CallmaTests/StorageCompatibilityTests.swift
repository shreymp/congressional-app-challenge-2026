import Foundation
import XCTest
@testable import Callma

final class StorageCompatibilityTests: XCTestCase {
    func testExistingFilesUnderEitherNameRemainReadableAndUntouched() throws {
        let base = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: base) }
        for name in ["phone-v1.json", "safety-v1.json"] {
            let current = base.appendingPathComponent("Callma/" + name)
            let legacy = base.appendingPathComponent("Callshield/" + name)
            XCTAssertEqual(AppStoragePaths.file(name, base: base), current)
            try FileManager.default.createDirectory(at: legacy.deletingLastPathComponent(), withIntermediateDirectories: true)
            let legacyData = Data("legacy content".utf8)
            try legacyData.write(to: legacy)
            XCTAssertEqual(AppStoragePaths.file(name, base: base), legacy)
            XCTAssertEqual(try Data(contentsOf: AppStoragePaths.file(name, base: base)), legacyData)
            try FileManager.default.createDirectory(at: current.deletingLastPathComponent(), withIntermediateDirectories: true)
            let currentData = Data("current content".utf8)
            try currentData.write(to: current)
            XCTAssertEqual(AppStoragePaths.file(name, base: base), current)
            XCTAssertEqual(try Data(contentsOf: current), currentData)
            XCTAssertEqual(try Data(contentsOf: legacy), legacyData)
        }
    }
}
