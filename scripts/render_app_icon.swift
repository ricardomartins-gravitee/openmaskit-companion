import AppKit
import Foundation

guard CommandLine.arguments.count == 2 else {
  fputs("usage: swift scripts/render_app_icon.swift OUTPUT.png\n", stderr)
  exit(2)
}

let edge = 1024
let bitmap = NSBitmapImageRep(
  bitmapDataPlanes: nil,
  pixelsWide: edge,
  pixelsHigh: edge,
  bitsPerSample: 8,
  samplesPerPixel: 4,
  hasAlpha: true,
  isPlanar: false,
  colorSpaceName: .deviceRGB,
  bytesPerRow: 0,
  bitsPerPixel: 0
)!

NSGraphicsContext.saveGraphicsState()
let graphics = NSGraphicsContext(bitmapImageRep: bitmap)!
NSGraphicsContext.current = graphics
graphics.imageInterpolation = .high

let canvas = NSRect(x: 0, y: 0, width: edge, height: edge)
NSColor.clear.setFill()
NSBezierPath(rect: canvas).fill()
NSColor(red: 11 / 255, green: 18 / 255, blue: 32 / 255, alpha: 1).setFill()
NSBezierPath(
  roundedRect: NSRect(x: 80, y: 80, width: 864, height: 864),
  xRadius: 190,
  yRadius: 190
).fill()

func color(hex: UInt32) -> NSColor {
  NSColor(
    red: CGFloat((hex >> 16) & 0xff) / 255,
    green: CGFloat((hex >> 8) & 0xff) / 255,
    blue: CGFloat(hex & 0xff) / 255,
    alpha: 1
  )
}

func drawLink(in rect: NSRect, angle: CGFloat, tint: NSColor) {
  NSGraphicsContext.saveGraphicsState()
  let center = NSPoint(x: rect.midX, y: rect.midY)
  let transform = NSAffineTransform()
  transform.translateX(by: center.x, yBy: center.y)
  transform.rotate(byDegrees: angle)
  transform.translateX(by: -center.x, yBy: -center.y)
  transform.concat()

  let capsule = NSBezierPath(
    roundedRect: rect,
    xRadius: rect.height / 2,
    yRadius: rect.height / 2
  )
  capsule.lineWidth = 50
  capsule.lineCapStyle = .round
  tint.setStroke()
  capsule.stroke()
  NSGraphicsContext.restoreGraphicsState()
}

drawLink(
  in: NSRect(x: 142, y: 452, width: 500, height: 188),
  angle: -38,
  tint: color(hex: 0x58a6ff)
)
drawLink(
  in: NSRect(x: 382, y: 384, width: 500, height: 188),
  angle: 38,
  tint: color(hex: 0x2dd4bf)
)

NSGraphicsContext.current = nil
NSGraphicsContext.restoreGraphicsState()

let output = URL(fileURLWithPath: CommandLine.arguments[1])
let png = bitmap.representation(using: .png, properties: [:])!
try png.write(to: output, options: .atomic)
