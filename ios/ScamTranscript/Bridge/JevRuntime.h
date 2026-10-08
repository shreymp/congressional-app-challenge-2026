#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
@interface JevRuntime : NSObject
- (nullable instancetype)initWithModelPath:(NSString *)path error:(NSError **)error;
- (nullable NSArray<NSNumber *> *)runInputIDs:(NSArray<NSNumber *> *)ids
                               attentionMask:(NSArray<NSNumber *> *)mask
                                   batchSize:(NSInteger)batchSize
                              sequenceLength:(NSInteger)sequenceLength
                                       error:(NSError **)error;
@end
NS_ASSUME_NONNULL_END
