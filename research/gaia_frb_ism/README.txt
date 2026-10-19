AstroDiscovery: Gaia / FRB / ISM 文献与数据，2026-10-19

这是围绕物理变量数学关系的定向文献集，不是对所有 Nature/Science 系列论文的穷尽综述。
共15篇：Gaia 5篇、FRB 5篇、ISM 5篇；期刊为Nature、Nature Astronomy、Science。
从出版社页面核实期刊、题目、关系与数据声明；全文来自出版社、arXiv及作者研究机构。

入口
- 本地浏览：playground/paper/index.html
- 可检索文献清单：本目录 catalog.csv / catalog.json（逐篇变量、关系类型和局限）
- 本地论文：playground/paper/{Gaia,FRB,ISM}/{name}.pdf
- 本地数据：data/{Gaia,FRB,ISM}/{name}/
- 下载来源与SHA256：download_manifest.json（50个下载文件，263626706字节）
- 本地表格转录说明：data/.../{name}/README.txt 或 LOCAL_NOTES.txt、PROVENANCE.json

优先用于符号回归试验
1. Chen_NatureAstronomy2023：双模RR Lyrae周期、周期比、金属丰度（303行）及视差样本（126行）。
2. Lian_NatureAstronomy2023：银河系径向金属丰度剖面，作者完整源数据已展开。
3. Xiang_Nature2022：247104颗亚巨星的年龄、丰度、轨道参数；区分厚盘与其他族群。
4. Feng_Science2022：退偏振函数及RM/散射关系；补充表S2转录7行，散射上限单独标识。
5. Chiang_NatureAstronomy2026：CO/[CII]光度密度、宇宙平均气体与恒星形成演化，Zenodo完整数据文件。
6. Kainulainen_Science2014：16朵分子云密度分布参数和恒星形成指标；第17行是合并统计，不能独立训练。

数据范围和缺口
- 已下载直接可获取的论文全文、作者数值表、相关补充附件，以及部分处理后的FITS产品。
- 7篇有独立机器可读作者/仓库数据：Xiang、Lian、Li2023、Chen、Li2021、Macquart、Chiang。
- 纸内表格文本/本地CSV转录与作者独立数据发布严格区分；未声称所有数据已机器可读或已复现论文。
- Feng ScienceDB V5：37个Stokes动态谱约3.73GB，保存元数据及入口，未全量下载。
- Macquart原始档案约5.34GB，仅取说明及3个小型定位FITS；作者GitHub快照包含7个事件，固定提交号见URL。
  快照为检索时的更新版本，部分DM已变，复现2020结果应以原论文Table 1和当时分析为准。
- Shannon：CSIRO公开切片/定位后验入口已记录，PB级原始带库未镜像。
- Kruijssen、Bruni：公开望远镜原始档案按论文项目号/入口定位，未全量镜像。
- Marigo：作者机器可读分析数据需请求；已保留包含参数表的公开补充材料。
- Chiang：两个Zenodo发布的6个文件全部下载，Code Ocean完整MCMC链未下载。
- Li2017与Li2021有勘误链接；当前收录公开稿未假定与所有勘误同步。
- probability distribution、统计相关性、已有物理模型检验，不等于新发现一个变量间确定公式，见逐篇分类。

校验和恢复（在仓库根目录运行）
  python scripts/research/fetch_papers.py --verify
  python scripts/research/fetch_papers.py --download
默认不联网、只列清单。恢复仅下载缺失文件，严格校验大小及SHA256，不覆盖已有改动文件。
下载ZIP后需自行解压；PDF转文本依赖pdftotext -layout。
  python scripts/research/extract_paper_tables.py
表格提取需先有对应PDF的同名.txt文本；两个CSV转录保留了原表的数值与单位。

文献、原始数据、缓存仍受现有.gitignore规则保护；Git只跟踪清单、研究说明和辅助脚本。
论文及数据遵守各自来源的许可，不随本仓库代码许可重新授权。
