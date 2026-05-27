import { describe, it, expectTypeOf } from "vitest";
import type { AnalysisResult, DriftResult, FeatureImportanceResult, BacktestResult } from "../api";

describe("AnalysisResult types", () => {
  it("drift is DriftResult | null", () => {
    expectTypeOf<AnalysisResult["drift"]>().toEqualTypeOf<DriftResult | null>();
  });
  it("feature_importance is FeatureImportanceResult | null", () => {
    expectTypeOf<AnalysisResult["feature_importance"]>().toEqualTypeOf<FeatureImportanceResult | null>();
  });
  it("backtest is BacktestResult | null", () => {
    expectTypeOf<AnalysisResult["backtest"]>().toEqualTypeOf<BacktestResult | null>();
  });
});
