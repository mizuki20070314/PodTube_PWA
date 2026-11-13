-- Child processes through posix_spawn (LuaJIT FFI): extra pipes on chosen descriptors, a clean environment, kill/wait.
-- (io.popen gives one pipe and no pid; the player needs separate video and audio pipes and a reliable way to stop.)
local ffi = require("ffi")

ffi.cdef [[
typedef struct { char opaque[256]; } pt_spawn_fa;
int pipe2(int fds[2], int flags);
int posix_spawn_file_actions_init(pt_spawn_fa *fa);
int posix_spawn_file_actions_destroy(pt_spawn_fa *fa);
int posix_spawn_file_actions_adddup2(pt_spawn_fa *fa, int fd, int newfd);
int posix_spawn_file_actions_addopen(pt_spawn_fa *fa, int fd, const char *path, int oflag, unsigned int mode);
int posix_spawn(int *pid, const char *file, const pt_spawn_fa *fa, const void *attr, char *const argv[], char *const envp[]);
int waitpid(int pid, int *status, int options);
int kill(int pid, int sig);
int fcntl(int fd, int cmd, ...);
int close(int fd);
int read(int fd, void *buf, unsigned int n);
extern char **environ;
]]

local C = ffi.C
local O_CLOEXEC = 0x80000
local F_DUPFD_CLOEXEC, F_SETPIPE_SZ = 1030, 1031
local O_RDONLY, O_WRONLY, O_CREAT, O_TRUNC = 0, 1, 0x40, 0x200
local WNOHANG = 1

local Proc = {}

-- the environment of children: ours without the LÖVE shims and with the system's libraries only
local function clean_env()
  local list = {}
  local i = 0
  while C.environ[i] ~= nil do
    local s = ffi.string(C.environ[i])
    if not s:match("^LD_PRELOAD=") and not s:match("^LD_LIBRARY_PATH=") then list[#list + 1] = s end
    i = i + 1
  end
  list[#list + 1] = "LD_LIBRARY_PATH=/usr/lib:/lib"
  return list
end

local function cstrings(list, keep)
  local arr = ffi.new("char*[?]", #list + 1)
  for i, s in ipairs(list) do
    local buf = ffi.new("char[?]", #s + 1)
    ffi.copy(buf, s)
    keep[#keep + 1] = buf
    arr[i - 1] = buf
  end
  arr[#list] = nil
  return arr
end

--- Proc.spawn(argv, opts) -> proc | nil, err
---   opts.pipes  = { {fd=3, size=1048576}, ... }   a pipe whose write end becomes descriptor `fd` of the child;
---                                                  proc.fds[fd] is the read end in this process
---   opts.log    = path for the child's stderr (stdout goes to /dev/null)
function Proc.spawn(argv, opts)
  opts = opts or {}
  local keep = {}
  local fa = ffi.new("pt_spawn_fa[1]")
  C.posix_spawn_file_actions_init(fa)
  local fds, closers = {}, {}
  -- stdin: /dev/null, stdout: /dev/null, stderr: log or /dev/null
  C.posix_spawn_file_actions_addopen(fa, 0, "/dev/null", O_RDONLY, 0)
  C.posix_spawn_file_actions_addopen(fa, 1, "/dev/null", O_WRONLY, 0)
  if opts.log then
    C.posix_spawn_file_actions_addopen(fa, 2, opts.log, O_WRONLY + O_CREAT + O_TRUNC, 420)
  else
    C.posix_spawn_file_actions_addopen(fa, 2, "/dev/null", O_WRONLY, 0)
  end
  for _, p in ipairs(opts.pipes or {}) do
    local pair = ffi.new("int[2]")
    if C.pipe2(pair, O_CLOEXEC) ~= 0 then return nil, "pipe2 failed" end
    -- keep our descriptors away from 0..9 so that dup2 in the child never maps a number onto itself
    local r = C.fcntl(pair[0], F_DUPFD_CLOEXEC, 10)
    local w = C.fcntl(pair[1], F_DUPFD_CLOEXEC, 10)
    C.close(pair[0]); C.close(pair[1])
    if r < 0 or w < 0 then return nil, "fcntl failed" end
    if p.size then C.fcntl(r, F_SETPIPE_SZ, ffi.cast("int", p.size)) end
    C.posix_spawn_file_actions_adddup2(fa, w, p.fd)
    fds[p.fd] = r
    closers[#closers + 1] = w
  end
  local list = {}
  for i, a in ipairs(argv) do list[i] = tostring(a) end
  local cargv = cstrings(list, keep)
  local cenv = cstrings(clean_env(), keep)
  local pid = ffi.new("int[1]")
  local rc = C.posix_spawn(pid, argv[1], fa, nil, cargv, cenv)
  C.posix_spawn_file_actions_destroy(fa)
  for _, w in ipairs(closers) do C.close(w) end        -- the child has its copies
  if rc ~= 0 then
    for _, r in pairs(fds) do C.close(r) end
    return nil, "posix_spawn failed (" .. rc .. ")"
  end
  return { pid = pid[0], fds = fds }
end

--- true when the process is gone (and reaps it)
function Proc.reap(proc)
  if not proc or proc.done then return true end
  local st = ffi.new("int[1]")
  local r = C.waitpid(proc.pid, st, WNOHANG)
  if r == proc.pid then
    proc.done = true
    proc.status = st[0]
    return true
  elseif r < 0 then
    -- ECHILD: SIGCHLD may be ignored, so the child is reaped by the system; ask whether it still exists
    if C.kill(proc.pid, 0) ~= 0 then proc.done = true; return true end
  end
  return false
end

function Proc.kill(proc, sig)
  if proc and not proc.done then C.kill(proc.pid, sig or 15) end
end

function Proc.close_fds(proc)
  for fd, r in pairs(proc.fds or {}) do C.close(r); proc.fds[fd] = nil end
end

return Proc
