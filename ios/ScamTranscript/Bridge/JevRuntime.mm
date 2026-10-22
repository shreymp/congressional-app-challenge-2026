#import "JevRuntime.h"
#include "onnxruntime_cxx_api.h"
#include <memory>
#include <vector>

@implementation JevRuntime {
    std::unique_ptr<Ort::Env> _environment;
    std::unique_ptr<Ort::Session> _session;
}

static void SetJevError(NSError **error, const std::exception &exception) {
    if (error) *error = [NSError errorWithDomain:@"ScamTranscript.Jev" code:1
        userInfo:@{NSLocalizedDescriptionKey: [NSString stringWithUTF8String:exception.what()]}];
}

- (nullable instancetype)initWithModelPath:(NSString *)path error:(NSError **)error {
    self = [super init];
    if (!self) return nil;
    try {
        _environment = std::make_unique<Ort::Env>(ORT_LOGGING_LEVEL_ERROR, "ScamTranscript.Jev");
        _environment->DisableTelemetryEvents();
        Ort::SessionOptions options;
        options.SetIntraOpNumThreads(2);
        options.SetInterOpNumThreads(1);
        options.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
        // CPU execution matches the existing Python adapter. No cloud service.
        _session = std::make_unique<Ort::Session>(*_environment, path.UTF8String, options);
    } catch (const std::exception &exception) { SetJevError(error, exception); return nil; }
    return self;
}

- (nullable NSArray<NSNumber *> *)runInputIDs:(NSArray<NSNumber *> *)ids
                               attentionMask:(NSArray<NSNumber *> *)mask
                                   batchSize:(NSInteger)batchSize
                              sequenceLength:(NSInteger)sequenceLength
                                       error:(NSError **)error {
    try {
        if ((batchSize != 1 && batchSize != 10) || sequenceLength < 1 || sequenceLength > 512 ||
            ids.count != batchSize * sequenceLength || mask.count != ids.count)
            throw std::runtime_error("Invalid Jev input tensor shape");
        std::vector<int64_t> inputIDs, attention;
        inputIDs.reserve(ids.count); attention.reserve(mask.count);
        for (NSNumber *value in ids) inputIDs.push_back(value.longLongValue);
        for (NSNumber *value in mask) attention.push_back(value.longLongValue);
        const int64_t shape[] = {batchSize, sequenceLength};
        auto memory = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
        std::vector<Ort::Value> inputs;
        inputs.push_back(Ort::Value::CreateTensor<int64_t>(memory, inputIDs.data(), inputIDs.size(), shape, 2));
        inputs.push_back(Ort::Value::CreateTensor<int64_t>(memory, attention.data(), attention.size(), shape, 2));
        const char *names[] = {"input_ids", "attention_mask"};
        const char *outputs[] = {"logits"};
        auto results = _session->Run(Ort::RunOptions{nullptr}, names, inputs.data(), 2, outputs, 1);
        auto info = results[0].GetTensorTypeAndShapeInfo();
        if (info.GetShape() != std::vector<int64_t>{batchSize, 25} ||
            info.GetElementType() != ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT)
            throw std::runtime_error("Unexpected Jev logits output");
        const float *logits = results[0].GetTensorData<float>();
        NSMutableArray<NSNumber *> *values = [NSMutableArray arrayWithCapacity:batchSize * 25];
        for (NSInteger index = 0; index < batchSize * 25; ++index) [values addObject:@(logits[index])];
        return values;
    } catch (const std::exception &exception) { SetJevError(error, exception); return nil; }
}
@end
