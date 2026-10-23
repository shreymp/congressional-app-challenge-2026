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

def config_list(name, settings):
    configs = []
    for mode in ["Debug", "Release"]:
        config = dict(settings)
        config.update(SWIFT_OPTIMIZATION_LEVEL="-Onone" if mode == "Debug" else "-O",
                      SWIFT_ACTIVE_COMPILATION_CONDITIONS="DEBUG" if mode == "Debug" else "",
                      DEBUG_INFORMATION_FORMAT="dwarf" if mode == "Debug" else "dwarf-with-dsym")
        configs.append(add(name + mode, "XCBuildConfiguration", name=mode, buildSettings=config))
    return add(name + "configs", "XCConfigurationList", buildConfigurations=configs,
               defaultConfigurationIsVisible=0, defaultConfigurationName="Debug")

project_settings = dict(IPHONEOS_DEPLOYMENT_TARGET="16.0", SDKROOT="iphoneos", SWIFT_VERSION="5.0",
                        CLANG_ENABLE_MODULES="YES", CLANG_ENABLE_OBJC_ARC="YES",
                        SWIFT_STRICT_CONCURRENCY="minimal", ENABLE_TESTABILITY="YES",
                        GCC_C_LANGUAGE_STANDARD="gnu17", CLANG_CXX_LANGUAGE_STANDARD="gnu++17")
project_config = config_list("project", project_settings)
app_id = ident("target:ScamTranscript")
targets, products, files = [], [], []
framework = ref("Vendor/libvosk.xcframework", "wrapper.xcframework")
files.append(framework)
ort_framework = ref("Vendor/ONNXRuntime/onnxruntime.xcframework", "wrapper.xcframework")
files.append(ort_framework)
for name, folder, product_type, extension in [
    ("ScamTranscript", "ScamTranscript", "com.apple.product-type.application", "app"),
    ("ScamTranscriptTests", "ScamTranscriptTests", "com.apple.product-type.bundle.unit-test", "xctest"),
    ("ScamTranscriptUITests", "ScamTranscriptUITests", "com.apple.product-type.bundle.ui-testing", "xctest"),
]:
    sources = []
    for path in sorted(path for path in (ROOT / folder).rglob("*") if path.suffix in (".swift", ".mm")):
        relative = str(path.relative_to(ROOT))
        file_id = ref(relative, "sourcecode.swift" if path.suffix == ".swift" else "sourcecode.cpp.objcpp")
        files.append(file_id)
        sources.append(build_file(file_id, relative))
    resources = []
    resource_paths = (["ScamTranscript/Resources/vosk-model-small-en-us-0.15", "ScamTranscript/Resources/Jev", "ScamTranscript/Resources/JevCallV1", "ScamTranscript/Resources/JevCallV2", "ScamTranscript/Resources/JevSignals.json", "ScamTranscript/Resources/Jev-NOTICE.txt", "Vendor/VOSK-LICENSE", "Vendor/ONNXRuntime/LICENSE"] if name == "ScamTranscript"
                      else ["ScamTranscriptTests/Fixtures"] if name == "ScamTranscriptTests" else [])
    for path in resource_paths:
        file_id = ref(path, "folder" if Path(path).suffix == "" and "LICENSE" not in path else "text")
        files.append(file_id)
        resources.append(build_file(file_id, path))
    phases = [add(name + "sources", "PBXSourcesBuildPhase", buildActionMask=2147483647, files=sources, runOnlyForDeploymentPostprocessing=0),
              add(name + "frameworks", "PBXFrameworksBuildPhase", buildActionMask=2147483647,
                  files=[build_file(framework, "vosk"), build_file(ort_framework, "ort")] if name == "ScamTranscript" else [], runOnlyForDeploymentPostprocessing=0),
              add(name + "resources", "PBXResourcesBuildPhase", buildActionMask=2147483647, files=resources, runOnlyForDeploymentPostprocessing=0)]
    product = add(name + "product", "PBXFileReference", explicitFileType="wrapper.application" if extension == "app" else "wrapper.cfbundle",
                  path=name + "." + extension, sourceTree="BUILT_PRODUCTS_DIR", includeInIndex=0)
    products.append(product)
    settings = dict(PRODUCT_NAME="$(TARGET_NAME)", PRODUCT_BUNDLE_IDENTIFIER="org.scamguardian." + name,
                    TARGETED_DEVICE_FAMILY="1", CODE_SIGN_STYLE="Automatic", GENERATE_INFOPLIST_FILE="YES")
    dependencies = []
    if name == "ScamTranscript":
        settings.update(INFOPLIST_FILE="ScamTranscript/App/Info.plist", GENERATE_INFOPLIST_FILE="NO",
                        SWIFT_OBJC_BRIDGING_HEADER="ScamTranscript/Bridge/ScamTranscript-Bridging-Header.h",
                        HEADER_SEARCH_PATHS=["$(SRCROOT)/ScamTranscript/Bridge", "$(SRCROOT)/Vendor/ONNXRuntime/Headers"],
                        OTHER_LDFLAGS=["$(inherited)", "-lc++", "-framework", "Accelerate", "-framework", "CoreML"],
                        LD_RUNPATH_SEARCH_PATHS="$(inherited) @executable_path/Frameworks")
    else:
        proxy = add(name + "proxy", "PBXContainerItemProxy", containerPortal=ident("project"), proxyType=1,
                    remoteGlobalIDString=app_id, remoteInfo="ScamTranscript")
        dependencies = [add(name + "dependency", "PBXTargetDependency", target=app_id, targetProxy=proxy)]
        settings.update(TEST_TARGET_NAME="ScamTranscript")
        if name == "ScamTranscriptTests":
            settings.update(TEST_HOST="$(BUILT_PRODUCTS_DIR)/ScamTranscript.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/ScamTranscript",
                            BUNDLE_LOADER="$(TEST_HOST)")
    targets.append(add("target:" + name, "PBXNativeTarget", name=name, productName=name,
                       buildConfigurationList=config_list(name, settings), buildPhases=phases,
                       buildRules=[], dependencies=dependencies, productReference=product, productType=product_type))

products_group = add("products", "PBXGroup", children=products, name="Products", sourceTree="<group>")
group = add("main", "PBXGroup", children=files + [products_group], sourceTree="<group>")
project = add("project", "PBXProject", attributes=dict(LastUpgradeCheck="2660", TargetAttributes={
    target: dict(CreatedOnToolsVersion="26.6", **({"TestTargetID": app_id} if target != app_id else {})) for target in targets}),
              buildConfigurationList=project_config, compatibilityVersion="Xcode 14.0", developmentRegion="en",
              hasScannedForEncodings=0, knownRegions=["en", "Base"], mainGroup=group,
              productRefGroup=products_group, projectDirPath="", projectRoot="", targets=targets)

def encode(value, depth=0):
    if isinstance(value, dict):
        return "{\n" + "".join("\t" * (depth + 1) + json.dumps(str(k)) + " = " + encode(v, depth + 1) + ";\n" for k, v in value.items()) + "\t" * depth + "}"
    if isinstance(value, list):
        return "(" + ", ".join(encode(v, depth) for v in value) + ")"
    return str(value) if isinstance(value, int) else json.dumps(value)

directory = ROOT / "ScamTranscript.xcodeproj"
directory.mkdir(exist_ok=True)
(directory / "project.pbxproj").write_text("// !$*UTF8*$!\n" + encode(dict(archiveVersion=1, classes={}, objectVersion=56, objects=objects, rootObject=project)) + "\n")
scheme = directory / "xcshareddata/xcschemes"
scheme.mkdir(parents=True, exist_ok=True)
def reference(name):
    extension = "app" if name == "ScamTranscript" else "xctest"
    return f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{ident("target:" + name)}" BuildableName="{name}.{extension}" BlueprintName="{name}" ReferencedContainer="container:ScamTranscript.xcodeproj"/>'
(scheme / "ScamTranscript.xcscheme").write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2660" version="1.7">
<BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries>
<BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="YES" buildForArchiving="YES" buildForAnalyzing="YES">{reference("ScamTranscript")}</BuildActionEntry>
</BuildActionEntries></BuildAction>
<TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="YES"><Testables>
<TestableReference skipped="NO" parallelizable="NO">{reference("ScamTranscriptTests")}</TestableReference>
<TestableReference skipped="NO" parallelizable="NO">{reference("ScamTranscriptUITests")}</TestableReference>
</Testables></TestAction>
<LaunchAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" launchStyle="0" useCustomWorkingDirectory="NO" ignoresPersistentStateOnLaunch="NO" debugDocumentVersioning="YES" allowLocationSimulation="YES"><BuildableProductRunnable runnableDebuggingMode="0">{reference("ScamTranscript")}</BuildableProductRunnable></LaunchAction>
<ProfileAction buildConfiguration="Release" shouldUseLaunchSchemeArgsEnv="YES" savedToolIdentifier="" useCustomWorkingDirectory="NO" debugDocumentVersioning="YES"><BuildableProductRunnable runnableDebuggingMode="0">{reference("ScamTranscript")}</BuildableProductRunnable></ProfileAction>
<AnalyzeAction buildConfiguration="Debug"/><ArchiveAction buildConfiguration="Release" revealArchiveInOrganizer="YES"/>
</Scheme>
''')
print(directory)
