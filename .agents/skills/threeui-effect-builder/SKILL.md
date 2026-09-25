---
name: threeui-effect-builder
description: Fetches and extracts byte-exact authored source files for ThreeUI/DesignCode effects (e.g., Sylva Hero, Complete Shelf) from the official GitHub repository.
---

# ThreeUI Effect Builder Workflow

When the user asks to build or implement a specific ThreeUI effect (using prompt templates like `add-sylva-hero` or `add-complete-shelf-landing-page`), you MUST follow these exact steps rather than simulating or writing custom code:

1. **Clone the Verified Source:**
   Do not approximate the effect. Clone the official repository to a temporary directory in the workspace:
   `git clone https://github.com/MengTo/threeui.git ./.tmp-threeui`

2. **Locate and Extract Assets:**
   Read the user's prompt to identify the exact files needed (e.g., `public/landing-pages/inner-green-3d.html`, `three.min.js`, `lexend-latin.woff2`, images).
   Copy these files from the `.tmp-threeui` folder into the current project.

3. **Preserve Exact Paths:**
   Ensure the files are placed at the exact relative paths expected by the original document (e.g., placing `inner-green-3d.html` inside `public/landing-pages/` or `docs/landing-pages/`).

4. **Clean up:**
   Remove the temporary cloned repository:
   `rm -rf ./.tmp-threeui` (or equivalent Windows command like `Remove-Item -Recurse -Force .\.tmp-threeui`)

5. **Host the Document:**
   Load the local document in a full-size iframe (or directly if it's a standalone HTML project like the current workflow), retaining all authored interactions and local assets without external network requests.
