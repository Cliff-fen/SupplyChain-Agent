# SupplyChain Agent 供应链指标口径（演示版）

> 文档类型：指标口径 | 数据性质：合成演示数据 | 版本：2026-08-19
>
> 本文是 SupplyChain Agent 的演示知识库摘要，不复制任何商业数据库内容。指标命名参考公开的 [SCOR 数字标准](https://www.ascm.org/standards/scor-ds/) 与 [供应链 KPI 公开定义](https://www.oecd.org/industry/ind/).

## 生产达成率

定义：`SUM(completed_quantity) / NULLIF(SUM(planned_quantity), 0)`。按工厂、产品线和计划日期筛选后计算，结果以百分比展示。分母为零时返回空值并标记为不可计算。

## 供应商准时交付率

定义：已交付采购订单中，`delivered_date <= planned_date` 的订单数除以已交付订单总数。未交付订单不计入分母，但应在异常列表中单独展示。

## 库存安全度

定义：`quantity / NULLIF(safety_stock, 0)`。低于 1.0 表示低于安全库存，低于 0.5 为高风险。库存快照按 `snapshot_date` 取最新记录，禁止跨日期重复累加。

## 一次合格率

定义：`SUM(passed_quantity) / NULLIF(SUM(inspected_quantity), 0)`。返工数量不计入通过数量；质量异常需关联生产工单。

## 订单履约率

定义：`SUM(delivered_quantity) / NULLIF(SUM(ordered_quantity), 0)`。承诺日期已过且未足量交付的订单进入履约风险清单。

## 查询约束

所有指标查询必须只读，使用白名单表和租户对应的数据源。日期筛选默认使用最近 30 天；展示原始 SQL、筛选条件和本文件引用。
