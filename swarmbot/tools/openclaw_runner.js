// OpenClaw Runner Script (Node.js)
// This script is called by the Python bridge to execute OpenClaw skills.
// It tries to locate OpenClaw packages and invoke the skill function.
// Note: This is a stub/template. It needs to resolve the actual OpenClaw installation.

const fs = require('fs');
const path = require('path');

// Try to resolve OpenClaw package
// Assuming openclaw is installed globally or in current project
let openclaw;
try {
  openclaw = require('openclaw');
} catch (e) {
  // Fallback: try to find in adjacent directories if running from dev
  const localPaths = [
    path.resolve(__dirname, '../../../../openclaw'),
    path.resolve(__dirname, '../../../openclaw'),
    '/root/openclaw'
  ];
  for (const p of localPaths) {
    if (fs.existsSync(path.join(p, 'package.json'))) {
      try {
        // This is tricky as OpenClaw source is TS. We might need dist/ or ts-node.
        // For simplicity, we assume dist/ is built.
        const distPath = path.join(p, 'dist/index.js');
        if (fs.existsSync(distPath)) {
          openclaw = require(distPath);
          break;
        }
      } catch (err) {}
    }
  }
}

if (!openclaw) {
  console.error("OpenClaw not found in environment.");
  process.exit(1);
}

// Main Execution Logic
const [toolName, argsJson] = process.argv.slice(2);
if (!toolName) {
  // Discovery Mode: Print available tools
  // This depends on OpenClaw exposing a tool registry API
  if (openclaw.getTools) {
    const tools = openclaw.getTools();
    console.log(JSON.stringify(tools));
  } else {
    console.log("[]");
  }
  process.exit(0);
}

// Execution Mode
try {
  const args = JSON.parse(argsJson || '{}');
  
  // Find and execute tool
  // Depending on OpenClaw API: openclaw.executeTool(name, args)
  if (openclaw.executeTool) {
    openclaw.executeTool(toolName, args).then(result => {
      console.log(JSON.stringify(result));
    }).catch(err => {
      console.error(err.message);
      process.exit(1);
    });
  } else {
    console.error("OpenClaw executeTool API not available.");
    process.exit(1);
  }
} catch (e) {
  console.error("Execution error: " + e.message);
  process.exit(1);
}
