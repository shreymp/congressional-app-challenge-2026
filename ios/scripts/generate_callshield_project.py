#!/usr/bin/env python3
"""Generate the checked-in Xcode project without third-party build tooling."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
objects = {}

def ident(name):
    return hashlib.sha256(name.encode()).hexdigest()[:24].upper()

def add(object_name, isa, **fields):
    key = ident(object_name)
    objects[key] = dict(isa=isa, **fields)
    return key

def ref(path, kind):
    return add("file:" + path, "PBXFileReference", lastKnownFileType=kind, path=path, sourceTree="<group>")

def build_file(reference, tag):
    return add("build:" + tag, "PBXBuildFile", fileRef=reference)

def config_list(name, settings, base=None):
    configs = []
    for mode in ["Debug", "Release"]:
        config = dict(settings)
        config.update(SWIFT_OPTIMIZATION_LEVEL="-Onone" if mode == "Debug" else "-O",
                      SWIFT_ACTIVE_COMPILATION_CONDITIONS="DEBUG" if mode == "Debug" else "",
                      DEBUG_INFORMATION_FORMAT="dwarf" if mode == "Debug" else "dwarf-with-dsym")
        fields = dict(name=mode, buildSettings=config)
        if base:
            fields.update(baseConfigurationReference=base)
        configs.append(add(name + mode, "XCBuildConfiguration", **fields))
    return add(name + "configs", "XCConfigurationList", buildConfigurations=configs,
               defaultConfigurationIsVisible=0, defaultConfigurationName="Debug")

def write(path, text):
    # Bytes, not write_text: the same UTF-8/LF output on macOS and Windows.
    path.write_bytes(text.encode("utf-8"))

project_settings = dict(IPHONEOS_DEPLOYMENT_TARGET="16.0", SDKROOT="iphoneos", SWIFT_VERSION="5.0",
                        CLANG_ENABLE_MODULES="YES", CLANG_ENABLE_OBJC_ARC="YES",
                        SWIFT_STRICT_CONCURRENCY="minimal", ENABLE_TESTABILITY="YES",
                        GCC_C_LANGUAGE_STANDARD="gnu17", CLANG_CXX_LANGUAGE_STANDARD="gnu++17")
project_config = config_list("project", project_settings)
app_id = ident("target:Callshield")
targets, products, files = [], [], []
# App settings a developer may override (bundle identifier, CALLSHIELD_*, APS_ENVIRONMENT) are defaults in this
# xcconfig, which ends by including the untracked Local.xcconfig. Target buildSettings would override both.
app_xcconfig = ref("Configuration/Callshield.xcconfig", "text.xcconfig")
# LiveKit Swift SDK: a remote Swift package linked into the app target and CallshieldTests (see below).
livekit_package = add("package:client-sdk-swift", "XCRemoteSwiftPackageReference",
                      repositoryURL="https://github.com/livekit/client-sdk-swift",
                      requirement=dict(kind="exactVersion", version="2.17.0"))
livekit = add("product:Callshield:LiveKit", "XCSwiftPackageProductDependency", package=livekit_package, productName="LiveKit")
for name, folder, product_type, extension in [
    ("Callshield", "Callshield", "com.apple.product-type.application", "app"),
    ("CallshieldTests", "CallshieldTests", "com.apple.product-type.bundle.unit-test", "xctest"),
    ("CallshieldUITests", "CallshieldUITests", "com.apple.product-type.bundle.ui-testing", "xctest"),
]:
    sources = []
    # Sort by case-sensitive path components and use "/" so ids and order match on macOS and Windows.
    for path in sorted((path for path in (ROOT / folder).rglob("*") if path.suffix in (".swift", ".mm")),
                       key=lambda path: path.relative_to(ROOT).parts):
        relative = path.relative_to(ROOT).as_posix()
        file_id = ref(relative, "sourcecode.swift" if path.suffix == ".swift" else "sourcecode.cpp.objcpp")
        files.append(file_id)
        sources.append(build_file(file_id, relative))
    resources = []
    resource_paths = (["Callshield/Assets.xcassets", "Callshield/PrivacyInfo.xcprivacy"] if name == "Callshield" else [])
    if name == "CallshieldTests":
        resource_paths.append("CallshieldTests/Fixtures/deepfake-wire.json")
    for path in resource_paths:
        file_id = ref(path, "folder.assetcatalog" if path.endswith("xcassets") else "text.json" if path.endswith(".json") else "text.xml")
        files.append(file_id)
        resources.append(build_file(file_id, path))
    package_product = livekit if name == "Callshield" else None
    if name == "CallshieldTests":
        # `@testable import Callshield` pulls in LiveKit's C modules, so this target needs its own product dependency and link too.
        # If the Mac test build reports LiveKit "linked as a static library" by both targets (duplicate code), try this first:
        # keep the dependency (module visibility) and stop creating this target's PBXBuildFile on the `frameworks =` line below
        # (frameworks stays empty; do not call add() for it, or an orphan build file is left). Untested; see CALLSHIELD.md.
        package_product = add("product:CallshieldTests:LiveKit", "XCSwiftPackageProductDependency", package=livekit_package, productName="LiveKit")
    frameworks = [add("build:product:" + name + ":LiveKit", "PBXBuildFile", productRef=package_product)] if package_product else []
    phases = [add(name + "sources", "PBXSourcesBuildPhase", buildActionMask=2147483647, files=sources, runOnlyForDeploymentPostprocessing=0),
              add(name + "frameworks", "PBXFrameworksBuildPhase", buildActionMask=2147483647,
                  files=frameworks, runOnlyForDeploymentPostprocessing=0),
              add(name + "resources", "PBXResourcesBuildPhase", buildActionMask=2147483647, files=resources, runOnlyForDeploymentPostprocessing=0)]
    product = add(name + "product", "PBXFileReference", explicitFileType="wrapper.application" if extension == "app" else "wrapper.cfbundle",
                  path=name + "." + extension, sourceTree="BUILT_PRODUCTS_DIR", includeInIndex=0)
    products.append(product)
    settings = dict(PRODUCT_NAME="$(TARGET_NAME)", PRODUCT_BUNDLE_IDENTIFIER="org.callshield." + name,
                    TARGETED_DEVICE_FAMILY="1", CODE_SIGN_STYLE="Automatic", GENERATE_INFOPLIST_FILE="YES")
    dependencies = []
    if name == "Callshield":
        del settings["PRODUCT_BUNDLE_IDENTIFIER"]  # Configuration/Callshield.xcconfig
        settings.update(INFOPLIST_FILE="Callshield/App/Info.plist", GENERATE_INFOPLIST_FILE="NO",
                        ASSETCATALOG_COMPILER_APPICON_NAME="AppIcon",
                        LD_RUNPATH_SEARCH_PATHS="$(inherited) @executable_path/Frameworks",
                        CODE_SIGN_ENTITLEMENTS="$(CALLSHIELD_ENTITLEMENTS_FILE)")
    else:
        proxy = add(name + "proxy", "PBXContainerItemProxy", containerPortal=ident("project"), proxyType=1,
                    remoteGlobalIDString=app_id, remoteInfo="Callshield")
        dependencies = [add(name + "dependency", "PBXTargetDependency", target=app_id, targetProxy=proxy)]
        settings.update(TEST_TARGET_NAME="Callshield")
        if name == "CallshieldTests":
            settings.update(TEST_HOST="$(BUILT_PRODUCTS_DIR)/Callshield.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/Callshield",
                            BUNDLE_LOADER="$(TEST_HOST)")
    targets.append(add("target:" + name, "PBXNativeTarget", name=name, productName=name,
                       buildConfigurationList=config_list(name, settings, app_xcconfig if name == "Callshield" else None),
                       buildPhases=phases, buildRules=[], dependencies=dependencies, productReference=product,
                       productType=product_type, **(dict(packageProductDependencies=[package_product]) if package_product else {})))

for path in ["Configuration/VoIP.entitlements", "Configuration/DefaultCalling.entitlements", "Configuration/DefaultDialer.entitlements"]:
    files.append(ref(path, "text.plist.entitlements"))
files.append(app_xcconfig)

products_group = add("products", "PBXGroup", children=products, name="Products", sourceTree="<group>")
group = add("main", "PBXGroup", children=files + [products_group], sourceTree="<group>")
project = add("project", "PBXProject", attributes=dict(LastUpgradeCheck="2660", TargetAttributes={
    target: dict(CreatedOnToolsVersion="26.6", **({"TestTargetID": app_id} if target != app_id else {})) for target in targets}),
              buildConfigurationList=project_config, compatibilityVersion="Xcode 14.0", developmentRegion="en",
              hasScannedForEncodings=0, knownRegions=["en", "Base"], mainGroup=group, packageReferences=[livekit_package],
              productRefGroup=products_group, projectDirPath="", projectRoot="", targets=targets)

def encode(value, depth=0):
    if isinstance(value, dict):
        return "{\n" + "".join("\t" * (depth + 1) + json.dumps(str(k)) + " = " + encode(v, depth + 1) + ";\n" for k, v in value.items()) + "\t" * depth + "}"
    if isinstance(value, list):
        return "(" + ", ".join(encode(v, depth) for v in value) + ")"
    return str(value) if isinstance(value, int) else json.dumps(value)

directory = ROOT / "Callshield.xcodeproj"
directory.mkdir(exist_ok=True)
write(directory / "project.pbxproj", "// !$*UTF8*$!\n" + encode(dict(archiveVersion=1, classes={}, objectVersion=56, objects=objects, rootObject=project)) + "\n")
scheme = directory / "xcshareddata/xcschemes"
scheme.mkdir(parents=True, exist_ok=True)
def reference(name):
    extension = "app" if name == "Callshield" else "xctest"
    return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{ident("target:" + name)}" BuildableName="{name}.{extension}" BlueprintName="{name}" ReferencedContainer="container:Callshield.xcodeproj"/>'
write(scheme / "Callshield.xcscheme", f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2660" version="1.7">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries>
<BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{reference("Callshield")}</BuildActionEntry>
</BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables>
<TestableReference skipped="NO" parallelizable="NO">{reference("CallshieldTests")}</TestableReference>
<TestableReference skipped="NO" parallelizable="NO">{reference("CallshieldUITests")}</TestableReference>
</Testables></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{reference("Callshield")}</BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{reference("Callshield")}</BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
''')
print(directory)
