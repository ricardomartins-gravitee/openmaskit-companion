// swift-tools-version: 5.9
import PackageDescription

let package = Package(
  name: "OpenMaskitCompanion",
  platforms: [.macOS(.v14)],
  products: [.executable(name: "OpenMaskitCompanion", targets: ["OpenMaskitCompanion"])],
  dependencies: [
    .package(
      url: "https://github.com/ricardomartins-gravitee/openmaskit-design-system.git",
      revision: "4a3024357273354309ba21c72b427e094c99be88")
  ],
  targets: [
    .target(name: "CompanionPolicy"),
    .target(name: "CompanionDesktopCore", dependencies: ["CompanionPolicy"]),
    .executableTarget(
      name: "OpenMaskitCompanion",
      dependencies: [
        "CompanionPolicy", "CompanionDesktopCore",
        .product(name: "OpenMaskitDesign", package: "openmaskit-design-system"),
      ]),
    .testTarget(name: "CompanionPolicyTests", dependencies: ["CompanionPolicy"]),
    .testTarget(name: "CompanionDesktopCoreTests", dependencies: ["CompanionDesktopCore"]),
  ]
)
