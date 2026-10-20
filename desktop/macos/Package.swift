// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "OpenMaskitCompanion",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "OpenMaskitCompanion", targets: ["OpenMaskitCompanion"])],
    targets: [
        .target(name: "CompanionPolicy"),
        .executableTarget(name: "OpenMaskitCompanion", dependencies: ["CompanionPolicy"]),
        .testTarget(name: "CompanionPolicyTests", dependencies: ["CompanionPolicy"])
    ]
)
