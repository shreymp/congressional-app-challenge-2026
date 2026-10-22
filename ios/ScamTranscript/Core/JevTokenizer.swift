import Foundation

/// Byte-level BPE for this bundle's NFC/ByteLevel/TemplateProcessing tokenizer.
/// Golden tests compare full prompts with the existing Hugging Face tokenizer.
final class JevTokenizer {
    private let vocab: [String: Int64]
    private let inverseVocab: [Int64: String]
    private let ranks: [String: Int]
    private let byteCharacters: [String]
    private let characterBytes: [Unicode.Scalar: UInt8]
    private let added: [(content: String, id: Int64, special: Bool)]
    private let addedRegex: NSRegularExpression
    private let piecesRegex: NSRegularExpression
    private var cache: [String: [Int64]] = [:]
    let paddingID: Int64 = 50283

    init(url: URL) throws {
        guard let json = try JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any],
              let model = json["model"] as? [String: Any], model["type"] as? String == "BPE",
              let values = model["vocab"] as? [String: Int64],
              let merges = model["merges"] as? [[String]],
              let additions = json["added_tokens"] as? [[String: Any]],
              (json["normalizer"] as? [String: Any])?["type"] as? String == "NFC" else {
            throw JevError.invalidTokenizer
        }
        vocab = values
        inverseVocab = Dictionary(uniqueKeysWithValues: values.map { ($0.value, $0.key) })
        ranks = Dictionary(uniqueKeysWithValues: merges.enumerated().map { ($0.element.joined(separator: "\0"), $0.offset) })
        let sorted = additions.sorted { ($0["content"] as? String ?? "").count > ($1["content"] as? String ?? "").count }
        added = try sorted.map {
            guard let content = $0["content"] as? String, let id = $0["id"] as? Int64,
                  let special = $0["special"] as? Bool else { throw JevError.invalidTokenizer }
            return (content, id, special)
        }
        let patterns = sorted.map { item -> String in
            let left = item["lstrip"] as? Bool == true ? #"\s*"# : ""
            let right = item["rstrip"] as? Bool == true ? #"\s*"# : ""
            return "(" + left + NSRegularExpression.escapedPattern(for: item["content"] as? String ?? "") + right + ")"
        }
        addedRegex = try NSRegularExpression(pattern: patterns.joined(separator: "|"))
        piecesRegex = try NSRegularExpression(pattern: #"'s|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)|\s+"#)
        var bytes = Array(33...126) + Array(161...172) + Array(174...255)
        var scalars = bytes
        var extra = 0
        for byte in 0...255 where !bytes.contains(byte) {
            bytes.append(byte); scalars.append(256 + extra); extra += 1
        }
        var mapping = Array(repeating: "", count: 256)
        var reverse: [Unicode.Scalar: UInt8] = [:]
        for (byte, scalar) in zip(bytes, scalars) {
            let character = Unicode.Scalar(scalar)!
            mapping[byte] = String(character)
            reverse[character] = UInt8(byte)
        }
        byteCharacters = mapping
        characterBytes = reverse
    }

    func encode(_ text: String, specialTokens: Bool = true) throws -> [Int64] {
        let normalized = text.precomposedStringWithCanonicalMapping as NSString
        var ids: [Int64] = []
        var cursor = 0
        for match in addedRegex.matches(in: normalized as String, range: NSRange(location: 0, length: normalized.length)) {
            ids += try encodeOrdinary(normalized.substring(with: NSRange(location: cursor, length: match.range.location - cursor)))
            guard let index = added.indices.first(where: { match.range(at: $0 + 1).location != NSNotFound }) else {
                throw JevError.invalidTokenizer
            }
            ids.append(added[index].id)
            cursor = NSMaxRange(match.range)
        }
        ids += try encodeOrdinary(normalized.substring(from: cursor))
        return specialTokens ? [50281] + ids + [50282] : ids
    }

    func decode(_ ids: [Int64]) throws -> String {
        let special = Set(added.filter(\.special).map(\.id))
        let addedValues = Dictionary(uniqueKeysWithValues: added.map { ($0.id, $0.content) })
        var bytes: [UInt8] = []
        for id in ids where !special.contains(id) {
            if let literal = addedValues[id] { bytes += Array(literal.utf8); continue }
            guard let token = inverseVocab[id] else { throw JevError.invalidTokenizer }
            for scalar in token.unicodeScalars {
                guard let byte = characterBytes[scalar] else { throw JevError.invalidTokenizer }
                bytes.append(byte)
            }
        }
        return String(decoding: bytes, as: UTF8.self)
    }

    private func encodeOrdinary(_ text: String) throws -> [Int64] {
        let source = text as NSString
        return try piecesRegex.matches(in: text, range: NSRange(location: 0, length: source.length)).flatMap { match in
            let piece = source.substring(with: match.range)
            if let cached = cache[piece] { return cached }
            var tokens = piece.utf8.map { byteCharacters[Int($0)] }
            while tokens.count > 1 {
                var bestRank = Int.max
                var bestPair: (String, String)?
                for index in 0..<(tokens.count - 1) {
                    if let rank = ranks[tokens[index] + "\0" + tokens[index + 1]], rank < bestRank {
                        bestRank = rank; bestPair = (tokens[index], tokens[index + 1])
                    }
                }
                guard let pair = bestPair else { break }
                var merged: [String] = []
                var index = 0
                while index < tokens.count {
                    if index + 1 < tokens.count, tokens[index] == pair.0, tokens[index + 1] == pair.1 {
                        merged.append(tokens[index] + tokens[index + 1]); index += 2
                    } else { merged.append(tokens[index]); index += 1 }
                }
                tokens = merged
            }
            let result = try tokens.map { token -> Int64 in
                guard let id = vocab[token] else { throw JevError.invalidTokenizer }
                return id
            }
            if cache.count > 4096 { cache.removeAll(keepingCapacity: true) }
            cache[piece] = result
            return result
        }
    }
}
