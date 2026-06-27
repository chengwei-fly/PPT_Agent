# 5 Typical PPTX Sample Fixtures (T010)

Per Constitution §VI "测试驱动与质量门禁", this directory MUST contain **5 real PPTX samples** covering the main use cases:

| # | File | Category | Use case | Min slides | Min distinct visual layouts |
|---|------|----------|----------|------------|----------------------------|
| 1 | `汇报-template.pptx` | 报告 | 季度/年度工作汇报 | 10 | 4 (cover / toc / body / closing) |
| 2 | `培训-template.pptx` | 培训 | 内部培训课件 | 12 | 5 (cover / toc / section / body / closing) |
| 3 | `方案-template.pptx` | 方案 | 项目方案/招标书 | 14 | 6 (cover / toc / overview / approach / plan / appendix) |
| 4 | `数据-template.pptx` | 数据 | 数据分析报告 | 10 | 5 (cover / toc / chart / insight / closing) |
| 5 | `营销-template.pptx` | 营销 | 市场活动/营销提案 | 8 | 4 (cover / feature / case / contact) |

## Adding Real Samples

> **Important**: Tests MUST use real PPTX (not synthetic) so the parser's edge cases are exercised.

To add a new sample:

1. Create a 10+ slide PPTX in PowerKey/Keynote/WPS
2. Save as `.pptx` (OOXML, not binary)
3. Strip any PII (phone/email/customer name) before committing
4. Add SHA-256 hash to the file name: `汇报-template_<hash8>.pptx`
5. Add a corresponding entry in `seed_samples.py` SAMPLES list

## Placeholder Generation

The `make seed` / `seed_samples.py` script will **auto-generate placeholder PPTX files** if the real fixtures are missing (useful for CI where the binaries cannot be committed). Placeholders are minimal 1-slide files; they validate the seeding pipeline but do NOT exercise the parser's edge cases.

## Why Real Samples?

The PPTX parser must handle:

- Different layout types (title slide, two-column, three-column, comparison, etc.)
- Embedded images, charts, SmartArt
- Custom theme colors and fonts
- Multi-language content (CJK + Latin)
- Large slide counts (≥ 50 pages stress test)
- Edge cases: empty slides, slides with only images, transitions

A synthetic 1-slide PPTX misses 90% of these cases. Real fixtures are how we catch regressions like "the parser breaks on charts in slide 7".

## CI Behavior

- `make test` uses real fixtures if present
- `make test` falls back to placeholders with a warning if not
- `make test-perf` requires real fixtures (validates SC-001 P95 latency)
