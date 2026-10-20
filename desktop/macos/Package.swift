// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "OpenMaskitCompanion",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "OpenMaskitCompanion", targets: ["OpenMaskitCompanion"])],
    targets: [.executableTarget(name: "OpenMaskitCompanion")]
)
