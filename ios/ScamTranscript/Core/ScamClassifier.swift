import Foundation

/// An explainable English baseline. Scores are rule weights, never probabilities.
struct ScamClassifier {
    enum Level: String { case insufficient = "Waiting for speech", clear = "No strong indicators", caution = "Caution", high = "High concern" }
    struct Signal: Equatable {
        let id: String
        let label: String
        let weight: Int
        let evidence: String
    }
    struct Assessment: Equatable {
        let level: Level
        let score: Int
        let signals: [Signal]
    }
    private struct Rule {
        let id: String
        let label: String
        let weight: Int
        let pattern: String
        var suppressNegatedRequest = true
    }

    // Match requests, not isolated topic words such as "bank" or "gift card".
    private let rules: [Rule] = [
        Rule(id: "code", label: "Verification-code request", weight: 4,
             pattern: #"\b(?:tell|read|give|send|share|provide|confirm|repeat)(?:\s+(?:me|us|your|the|a|that|this|back|out|loud|please|to)){0,6}\s+(?:verification|security|one time|otp|authentication|six digit|two factor)\s*(?:code|pin)?\b|\b(?:tell|read|give|send|share|provide|repeat)(?:\s+(?:me|us|your|the|a|that|this|back|out|loud|please|to)){0,6}\s+code\b"#),
        Rule(id: "credentials", label: "Password or PIN request", weight: 5,
             pattern: #"\b(?:tell|read|give|send|share|provide|confirm)(?:\s+(?:me|us|your|the|a|that|this|back|out|loud|please|to)){0,6}\s+(?:password|passcode|pin|login details)\b"#),
        Rule(id: "payment", label: "Unusual payment request", weight: 4,
             pattern: #"\bpay(?:\s+\w+){0,8}\s+gift cards?\b|\b(?:pay|send|transfer|deposit|wire)(?:\s+\w+){0,8}\s+(?:bitcoin|crypto(?:currency)?|wire transfer)\b|\b(?:read|send|give|tell)(?:\s+\w+){0,6}\s+gift card(?:\s+\w+){0,3}\s+(?:numbers?|codes?)\b"#),
        Rule(id: "remote", label: "Remote access request", weight: 4,
             pattern: #"\b(?:install|download|open)(?:\s+\w+){0,5}\s+(?:anydesk|teamviewer|remote access|remote desktop)\b"#),
        Rule(id: "identity", label: "Sensitive identity request", weight: 3,
             pattern: #"\b(?:tell|give|send|share|provide|confirm)(?:\s+(?:me|us|your|the|a|that|this|please|to)){0,6}\s+(?:social security|credit card|debit card|bank account)(?:\s+number)?\b"#),
        Rule(id: "secrecy", label: "Secrecy or isolation", weight: 2,
             pattern: #"\b(?:do not|never)\s+(?:tell|discuss|talk to|contact)(?:\s+\w+){0,3}\s+(?:anyone|anybody|family|bank|police)\b|\bkeep\s+(?:this|it)(?:\s+\w+){0,2}\s+(?:secret|confidential)\b"#,
             suppressNegatedRequest: false),
        Rule(id: "pressure", label: "Pressure to stay on the line", weight: 1,
             pattern: #"\b(?:do not hang up|stay on the (?:phone|line)|cannot hang up)\b"#,
             suppressNegatedRequest: false),
        Rule(id: "threat", label: "Threat or account loss", weight: 2,
             pattern: #"\b(?:you will be arrested|warrant for your arrest|account (?:will be|is being) (?:closed|blocked|suspended)|police (?:will|are going to) arrest)\b"#),
        Rule(id: "urgency", label: "Immediate action demand", weight: 1,
             pattern: #"\b(?:right now|immediately|act now|urgent|within (?:ten|10|five|5) minutes)\b"#)
    ]

    func assess(_ transcript: String) -> Assessment {
        let text = Self.normalize(transcript)
        guard text.split(separator: " ").count >= 3 else {
            return Assessment(level: .insufficient, score: 0, signals: [])
        }
        let nsText = text as NSString
        let signals = rules.compactMap { rule -> Signal? in
            guard let regex = try? NSRegularExpression(pattern: rule.pattern) else { return nil }
            for match in regex.matches(in: text, range: NSRange(location: 0, length: nsText.length)) {
                if rule.suppressNegatedRequest && Self.isNegated(match.range, in: text) { continue }
                return Signal(id: rule.id, label: rule.label, weight: rule.weight,
                              evidence: nsText.substring(with: match.range))
            }
            return nil
        }
        let score = signals.reduce(0) { $0 + $1.weight }
        // Weak cues alone never escalate a transcript to high concern.
        let hasStrongRequest = signals.contains { $0.weight >= 3 }
        let level: Level = hasStrongRequest && score >= 6 ? .high : score >= 3 ? .caution : .clear
        return Assessment(level: level, score: score, signals: signals)
    }

    private static func normalize(_ text: String) -> String {
        let expanded = text.lowercased().replacingOccurrences(of: "’", with: "'")
            .replacingOccurrences(of: "don't", with: "do not")
            .replacingOccurrences(of: "won't", with: "will not")
            .replacingOccurrences(of: "wouldn't", with: "would not")
        return expanded.replacingOccurrences(of: "[^a-z0-9.!?;]+", with: " ", options: .regularExpression)
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private static func isNegated(_ range: NSRange, in text: String) -> Bool {
        let before = (text as NSString).substring(to: range.location)
        let clause = before.components(separatedBy: CharacterSet(charactersIn: ".!?;")).last ?? before
        let afterContrast = clause.components(separatedBy: " but ").last ?? clause
        let prefix = afterContrast.split(separator: " ").suffix(5).joined(separator: " ")
        return prefix.range(of: #"\b(?:not|never|no one|nobody|avoid)\b"#, options: .regularExpression) != nil
    }
}

/// Final segments and the replaceable partial share a bounded window. Repeated
/// partial updates do not append duplicate words or accumulate rule weights.
struct TranscriptWindow {
    let maxWords: Int
    private(set) var finalized = ""
    private(set) var partial = ""
    init(maxWords: Int = 180) { precondition(maxWords > 0); self.maxWords = maxWords }
    var text: String { bounded([finalized, partial].filter { !$0.isEmpty }.joined(separator: " ")) }
    mutating func updatePartial(_ text: String) { partial = bounded(text) }
    mutating func commit(_ text: String) {
        finalized = bounded([finalized, text].filter { !$0.isEmpty }.joined(separator: " "))
        partial = ""
    }
    private func bounded(_ text: String) -> String {
        text.split(whereSeparator: \.isWhitespace).suffix(maxWords).joined(separator: " ")
    }
}
