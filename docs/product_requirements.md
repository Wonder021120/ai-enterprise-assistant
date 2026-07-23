# Product Requirements

## 1. Project name

暂定：CareerPilot AI

## 2. Target users

应届毕业生和初级岗位求职者，尤其是计算机、人工智能和数据相关专业的学生。

## 3. Core problem

用户看到招聘岗位后，通常难以快速判断岗位需要哪些技能和其他条件，也不清楚自己的背景是否匹配，以及是否值得优先投递。

本项目将帮助用户分析岗位技能要求、学历要求、毕业时间限制、工作经验、地点、招聘类型和薪资信息，并给出匹配分析和补强建议。

## 4. First version features

- 输入或粘贴招聘岗位 JD
- 提取公司、岗位名称、地点和招聘类型
- 提取必需技能和加分技能
- 提取学历、毕业时间和工作经验要求
- 提取 JD 中明确公开的薪资信息
- 对比用户背景与岗位要求
- 输出已满足要求、技能缺口和投递优先级
- 生成针对岗位的学习和项目建议

## 5. Features not included in the first version

- 自动批量爬取招聘网站
- 自动投递岗位
- 自动生成虚假项目经历
- 在缺少数据时猜测薪资
- 复杂前端界面
- 多用户和企业级权限系统

## 6. Planned technology stack

- Python
- FastAPI
- SQL
- PostgreSQL
- RAG
- LLM
- Docker
- Git and GitHub
