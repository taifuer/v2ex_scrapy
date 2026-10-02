import test from "node:test"
import assert from "node:assert/strict"
import { comparePerformance } from "./performance-comparison.mjs"

const report = values => ({ dataVersion: "same", conditions: { gzip: true }, results: values.map(readyMs => ({ name: "detail", readyMs })) })
test("compares medians without failing on a single outlier", () => {
  assert.equal(comparePerformance(report([4100, 4200, 12000]), report([4000, 4050, 4100]))[0].regression, false)
})
test("detects sustained slowdown and respects the absolute noise floor", () => {
  assert.equal(comparePerformance(report([4900, 5000, 5100]), report([3900, 4000, 4100]))[0].regression, true)
  assert.equal(comparePerformance(report([1300, 1400, 1500]), report([900, 1000, 1100]))[0].regression, false)
})
test("rejects changed datasets, conditions, cases, and insufficient samples", () => {
  const base = report([1000, 1100, 1200])
  assert.throws(() => comparePerformance({ ...base, dataVersion: "new" }, base), /same analysis data/)
  assert.throws(() => comparePerformance({ ...base, conditions: { gzip: false } }, base), /condition/)
  assert.throws(() => comparePerformance({ ...base, results: [] }, base), /same page cases/)
  assert.throws(() => comparePerformance(report([1000]), base), /three valid/)
})
