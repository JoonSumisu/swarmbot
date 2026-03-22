#!/bin/bash
# 清理不需要提交到 Git 的文件

echo "Cleaning up unnecessary files..."

# 移除 build 目录
rm -rf build/

# 移除所有 __pycache__ 目录
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

# 移除 agent_workspace 目录
rm -rf agent_workspace/

# 移除 .pyc 文件
find . -name "*.pyc" -delete 2>/dev/null

# 移除 artifacts 中的临时报告（保留最新的）
ls -t artifacts/*.json 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null

echo "Cleanup complete!"
echo ""
echo "Ready files summary:"
git status --short | grep -v "__pycache__" | grep -v "build/" | wc -l
echo "files to commit"
