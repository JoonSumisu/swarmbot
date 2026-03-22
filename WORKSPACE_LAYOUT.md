# Workspace 分层说明

本地开发采用双目录分层：

- `/root/swarmbot_dev`
  - 开发与实验目录
  - 允许放置评估脚本、实验产物、临时对比文件
  - 可包含 `artifacts/`、调试日志、A/B 测试代码

- `/root/swarmbot_git`
  - Git 准备目录（用于提交与上传）
  - 由 `swarmbot_dev` 的 Git worktree 派生
  - 目标是保持干净、可审查、无多余实验文件与隐私内容

## 推荐流程

1. 在 `swarmbot_dev` 完成开发与测试。
2. 确认需要提交的变更后，在 `swarmbot_git` 检查差异并提交。
3. 上传前在 `swarmbot_git` 再次确认无临时文件、无敏感信息。

## 常用命令

```bash
git -C /root/swarmbot_dev worktree add --detach /root/swarmbot_git HEAD
git -C /root/swarmbot_git status
```
