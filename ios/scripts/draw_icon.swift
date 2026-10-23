import AppKit

// Temporary asset only. Replace these exports when the team supplies final artwork.
// Usage: draw_icon OUTPUT [SIZE] [opaque|transparent|mono|background]
let output = CommandLine.arguments[1]
let size = CGFloat(Int(CommandLine.arguments.dropFirst(2).first ?? "1024") ?? 1024)
let mode = CommandLine.arguments.dropFirst(3).first ?? "opaque"
let bitmap = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size), pixelsHigh: Int(size), bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
let context = NSGraphicsContext(bitmapImageRep: bitmap)!
NSGraphicsContext.saveGraphicsState()
NSGraphicsContext.current = context
let bounds = NSRect(x: 0, y: 0, width: size, height: size)
NSColor.clear.setFill()
NSBezierPath(rect: bounds).fill()
if mode == "opaque" || mode == "background" {
    NSColor(srgbRed: 227.0/255, green: 238.0/255, blue: 1, alpha: 1).setFill()
    NSBezierPath(rect: bounds).fill()
}
if mode != "background" {
    let color = mode == "mono" ? NSColor.black : NSColor(srgbRed: 25.0/255, green: 94.0/255, blue: 217.0/255, alpha: 1)
    let box = NSRect(x: size * 0.21, y: size * 0.21, width: size * 0.58, height: size * 0.58)
    let path = NSBezierPath(roundedRect: box, xRadius: size * 0.065, yRadius: size * 0.065)
    path.lineWidth = size * 0.012
    let dash: [CGFloat] = [size * 0.028, size * 0.02]
    path.setLineDash(dash, count: dash.count, phase: 0)
    color.setStroke()
    path.stroke()
    let label = "logo" as NSString
    let attributes: [NSAttributedString.Key: Any] = [.font: NSFont.monospacedSystemFont(ofSize: size * 0.11, weight: .medium), .foregroundColor: color]
    let textSize = label.size(withAttributes: attributes)
    label.draw(at: NSPoint(x: (size - textSize.width)/2, y: (size - textSize.height)/2), withAttributes: attributes)
}
NSGraphicsContext.restoreGraphicsState()
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: output))
