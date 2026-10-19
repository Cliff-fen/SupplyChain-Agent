# UCI Online Retail II 公开交易数据来源说明

## 来源与数据边界

- 发布机构：University of California, Irvine Machine Learning Repository
- 数据集：[Online Retail II](https://archive.ics.uci.edu/dataset/502/online%2Bretail)
- 官方工作簿：[online_retail_II.xlsx](https://archive.ics.uci.edu/ml/machine-learning-databases/00502/online_retail_II.xlsx)
- 许可：CC BY 4.0
- 数据规模：1,067,371 条匿名化英国零售交易，覆盖 2009-12-01 至 2011-12-09。

数据字段包含发票号、货品编码、描述、数量、交易时间、单价、匿名客户标识和国家。
它适用于订单、需求趋势、商品结构、退货和区域交易分析；不包含供应商、工单、生产工厂或真实库存。因此项目将它落入独立的
`retail_transactions` 表，禁止将国家、客户或货品编码错误解释为现有制造演示库的组织实体。

## 导入与验证

导入器通过 HTTPS 直接下载官方工作簿，验证每个工作表的字段结构，并在事务行数少于一百万时中止。以源行号为幂等键，可安全重复运行：

```powershell
docker compose exec -T api python -m scripts.import_uci_online_retail
```
