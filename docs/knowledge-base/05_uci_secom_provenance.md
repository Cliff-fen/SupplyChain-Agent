# UCI SECOM 公开制造数据来源说明

## 来源与真实性

- 发布机构：University of California, Irvine Machine Learning Repository
- 数据集：SECOM（半导体制造过程控制数据）
- 官方页面：[UCI SECOM](https://archive.ics.uci.edu/dataset/179/secom)
- 官方归档：[secom.zip](https://archive.ics.uci.edu/static/public/179/secom.zip)
- 下载归档 SHA-256：`eea568ba f3c22290 9d6d7d29 4cf0b096 b5502bd9 6d92c0b8 0a65b847 14059be8`
- 数据规模：1,567 条记录、590 个传感器变量、时间戳和 -1/1 结果标签。

该数据集是公开发布的真实工业过程数据，不代表本项目任何客户或工厂。导入脚本会在下载时校验 SHA-256，校验失败会中止导入。

## 项目中的落库方式

表 `manufacturing_quality_events` 保留源行号、测量时间、结果标签、缺失传感器数量和前 10 个传感器变量。其余变量仍以 UCI 原始归档为准，避免未经验证地猜测变量含义。`dataset_source` 字段和本文件共同构成数据血缘记录。

导入命令：

```powershell
docker compose exec -T api python -m scripts.import_uci_secom
```
