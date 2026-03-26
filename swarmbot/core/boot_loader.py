from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


class BootLoader:
    """Boot 加载器
    支持 boot_config.json 配置，不同组件加载不同的 boot 文件。
    MasterAgent 是唯一加载 SOUL.md 的组件（角色设定）。
    """
    
    # 默认 boot 配置（无 SOUL.md 的组件）
    DEFAULT_CONFIG = {
        "master": {
            "files": [
                "master/SOUL.md",
                "master/IDENTITY.md",
                "master/USER.md",
                "master/masteragentboot.md"
            ],
            "include_shared": True
        },
        "inference": {
            "files": [
                "inference/inference_boot.md",
                "inference/inference_tools.md",
                "inference/swarmboot.md"
            ],
            "include_shared": True
        },
        "autonomous": {
            "files": [
                "autonomous/autonomous_boot.md"
            ],
            "include_shared": True
        },
        "analyst": {
            "files": [
                "inference/inference_boot.md"
            ],
            "include_shared": True
        },
        "worker": {
            "files": [
                "inference/inference_boot.md"
            ],
            "include_shared": True
        },
        "reflection": {
            "files": [
                "autonomous/bundles/reflection.md"
            ],
            "include_shared": False
        },
        "minimal": {
            "files": [],
            "include_shared": False
        }
    }
    
    def __init__(self, workspace: Optional[str] = None):
        """初始化 BootLoader"""
        self.workspace = Path(workspace or os.path.expanduser("~/.swarmbot"))
        self.user_boot_dir = self.workspace / "boot"
        self.package_boot_dir = Path(__file__).parent.parent / "boot"
        
        # 文件大小限制
        self.max_chars_per_file = 8000
        self.max_total_chars = 30000
        
        # 加载配置
        self.config = self._load_boot_config()
    
    def _load_boot_config(self) -> Dict:
        """加载 boot_config.json 配置"""
        # 优先从用户目录加载
        config_path = self.user_boot_dir / "boot_config.json"
        if config_path.exists():
            try:
                return json.loads(config_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[BootLoader] Failed to load {config_path}: {e}")
        
        # 其次从包内加载
        package_config = self.package_boot_dir / "boot_config.json"
        if package_config.exists():
            try:
                return json.loads(package_config.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[BootLoader] Failed to load {package_config}: {e}")
        
        # 使用默认配置
        return self.DEFAULT_CONFIG
    
    def _load_file(self, filename: str) -> str:
        """加载单个 boot 文件，优先从用户目录加载"""
        # 用户目录优先
        user_path = self.user_boot_dir / filename
        if user_path.exists():
            try:
                content = user_path.read_text(encoding="utf-8")
                return self._truncate_content(content, filename)
            except Exception as e:
                print(f"[BootLoader] Failed to load {user_path}: {e}")
        
        # 包内文件
        package_path = self.package_boot_dir / filename
        if package_path.exists():
            try:
                content = package_path.read_text(encoding="utf-8")
                return self._truncate_content(content, filename)
            except Exception as e:
                print(f"[BootLoader] Failed to load {package_path}: {e}")
        
        # 文件不存在
        return ""
    
    def _load_shared(self) -> str:
        """加载 shared 目录下的共享配置"""
        shared_files = []
        
        # 加载 TOOLS.md
        tools_content = self._load_file("shared/TOOLS.md")
        if tools_content:
            shared_files.append(f"### 共享工具配置\n{tools_content}")
        
        # 加载 HEARTBEAT.md
        heartbeat_content = self._load_file("shared/HEARTBEAT.md")
        if heartbeat_content:
            shared_files.append(f"### 共享心跳配置\n{heartbeat_content}")
        
        return "\n\n".join(shared_files)
    
    def _truncate_content(self, content: str, filename: str) -> str:
        """截断过长的文件内容"""
        if not content:
            return ""
        if len(content) <= self.max_chars_per_file:
            return content
        truncated = content[:self.max_chars_per_file]
        return f"{truncated}\n\n... [{filename} 截断，总长度 {len(content)} 字符]"
    
    def load_boot(self, boot_mode: str = "master", custom_files: List[str] = None) -> str:
        """加载并合并 boot 文件
        
        Args:
            boot_mode: boot 模式名称
            custom_files: 自定义文件列表（优先于 boot_mode）
        
        Returns:
            合并后的 boot 内容
        """
        if custom_files:
            # 使用自定义文件列表
            mode_config = {
                "files": custom_files,
                "include_shared": False
            }
        else:
            mode_config = self.config.get(boot_mode, self.DEFAULT_CONFIG.get(boot_mode, {"files": [], "include_shared": False}))
        
        sections = []
        total_chars = 0
        
        # 加载模式指定的文件
        files_to_load = mode_config.get("files", [])
        for filename in files_to_load:
            content = self._load_file(filename)
            if content:
                # 从文件路径提取显示名称
                display_name = filename.replace("/", " - ")
                section = f"### {display_name}\n{content}"
                
                if total_chars + len(section) > self.max_total_chars:
                    sections.append("... [boot 文件总长度超出限制，已截断]")
                    break
                
                sections.append(section)
                total_chars += len(section)
        
        # 可选：加载共享配置
        if mode_config.get("include_shared", False):
            shared = self._load_shared()
            if shared and total_chars + len(shared) <= self.max_total_chars:
                sections.append(shared)
        
        return "\n\n".join(sections)
    
    def get_boot_summary(self, boot_mode: str = "master") -> str:
        """获取 boot 文件摘要"""
        mode_config = self.config.get(boot_mode, self.DEFAULT_CONFIG.get(boot_mode, {"files": []}))
        files_to_load = mode_config.get("files", [])
        
        summaries = []
        for filename in files_to_load:
            content = self._load_file(filename)
            if content:
                summary = content[:200].replace("\n", " ").strip()
                summaries.append(f"- {filename}: {summary}...")
        
        return "\n".join(summaries) if summaries else "无 boot 文件"
    
    def list_available_files(self) -> List[str]:
        """列出所有可用的 boot 文件"""
        files = []
        
        # 用户目录
        if self.user_boot_dir.exists():
            for f in self.user_boot_dir.rglob("*.md"):
                rel = f.relative_to(self.user_boot_dir)
                files.append(f"user:{rel}")
        
        # 包内目录
        if self.package_boot_dir.exists():
            for f in self.package_boot_dir.rglob("*.md"):
                rel = f.relative_to(self.package_boot_dir)
                files.append(f"package:{rel}")
        
        return files
