# TOOLS.md - Technical Configuration

## 工具权限策略
- **File System**:
  - Allow Read: `/root/swarmbot`, `/root/workspace`
  - Allow Write: `/root/workspace/output`, `/root/workspace/cache`
  - Deny: `/etc`, `/var`, `/usr` (System directories)

- **Shell Execution**:
  - Allow: `ls`, `grep`, `cat`, `echo`, `mkdir`, `touch`, `git`, `python3`
  - Deny: `rm -rf /`, `mkfs`, `dd`

## 集成状态
- **OpenClaw Bridge**: Enabled (Auto-detect Node.js)
- **Local Browser**: Enabled (Headless Chrome)
- **QMD Memory**: Enabled (Vector + BM25)
