import AppKit
let image = NSImage(size: NSSize(width: 1024, height: 1024))
image.lockFocus()
NSColor(srgbRed: 36/255, green: 118/255, blue: 94/255, alpha: 1).setFill()
NSBezierPath(rect: NSRect(x: 0, y: 0, width: 1024, height: 1024)).fill()
let shield = NSBezierPath()
shield.move(to: NSPoint(x: 512, y: 790))
shield.curve(to: NSPoint(x: 732, y: 711), controlPoint1: NSPoint(x: 589, y: 750), controlPoint2: NSPoint(x: 655, y: 723))
shield.line(to: NSPoint(x: 732, y: 540))
shield.curve(to: NSPoint(x: 512, y: 231), controlPoint1: NSPoint(x: 732, y: 400), controlPoint2: NSPoint(x: 654, y: 308))
shield.curve(to: NSPoint(x: 292, y: 540), controlPoint1: NSPoint(x: 370, y: 308), controlPoint2: NSPoint(x: 292, y: 400))
shield.line(to: NSPoint(x: 292, y: 711))
shield.curve(to: NSPoint(x: 512, y: 790), controlPoint1: NSPoint(x: 369, y: 723), controlPoint2: NSPoint(x: 435, y: 750))
shield.close()
shield.lineWidth = 33
shield.lineJoinStyle = .round
NSColor.white.setStroke()
shield.stroke()
let check = NSBezierPath()
check.move(to: NSPoint(x: 410, y: 521))
check.line(to: NSPoint(x: 481, y: 450))
check.line(to: NSPoint(x: 619, y: 592))
check.lineWidth = 36
check.lineCapStyle = .round
check.lineJoinStyle = .round
check.stroke()
image.unlockFocus()
let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!
try bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: CommandLine.arguments[1]))
