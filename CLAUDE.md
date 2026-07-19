# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

B2BF Launcher: a Windows client and local network shim that lets a modern Battlefield 2 install talk to the
"Phoenix Network" (b2bf2.net / phoenixnetwork.net) backend. The original BF2 game binary expects to talk to
EA's defunct GameSpy master-server infrastructure; this launcher reimplements the relevant pieces of that
protocol locally so BF2 believes it's still 2005.

## Solution layout

`B2BF.Launcher.sln` has three projects:

- **B2BF.Common** (`net6.0`) — shared library with almost all real logic: account/OAuth handling, settings
  storage, the GameSpy protocol emulation, the local HTTP shim, and the game updater. Both other projects
  depend on it.
- **B2BF.Launcher** (`net6.0-windows`, WinForms, `OutputType=WinExe`) — the actual user-facing launcher app.
  `Form1` is effectively the whole UI/controller. Requires Windows to build (WinForms).
- **B2BF.Service** (`net8.0-windows`, Worker Service via `Microsoft.Extensions.Hosting.WindowsServices`) —
  scaffolded but not yet implemented; `Worker.cs` is still the default template heartbeat loop.

## Build

Requires the Windows .NET SDKs (net6.0-windows and net8.0-windows targets) — this cannot be fully built on
non-Windows.

```
dotnet build "B2BF.Launcher.sln"
dotnet build B2BF.Launcher\B2BF.Launcher.csproj
dotnet build B2BF.Common\B2BF.Common.csproj
dotnet build B2BF.Service\B2BF.Service.csproj
dotnet run --project B2BF.Launcher
```

There are no test projects and no lint config in the repo. `B2BF Launcher.aip` is an Advanced Installer
project used to package releases; it's not part of the normal dev loop.

## Architecture: why Form1 starts five servers

`Form1`'s constructor (`B2BF.Launcher/Form1.cs`) spins up a set of local listeners *before* the game ever
launches, because BF2 hardcodes connections to GameSpy's classic ports on `127.0.0.1`/its LAN-facing
interface. Each listener emulates one piece of that protocol, all living under
`B2BF.Common/Networking/GameSpy/`:

| Component | Transport / Port | Role |
|---|---|---|
| `Login/LoginServer` | TCP 29900, 29901 | Login + search/profile lookups (`LoginClient`, `SClient`) |
| `Search/SearchServer` | TCP 28910 | Server browser queries; builds responses via `GameSpyHelper.PackServerList` and the SQL-like filter parser (`FixFilter`) |
| `Report/ReportServer` | UDP 27900 | Server heartbeat/stat reporting protocol |
| `Networking/GameSpy/CdKey/CdKeyServer` | UDP 29910 | CD-key auth challenge/response the game performs against a "master" |
| `Networking/Http/HttpServer` | TCP 8888 | Local HTTP proxy: forwards BF2's in-game stats HTTP calls to `stats.b2bf2.net`, and doubles as the OAuth redirect target (`/oauthloginreturn`) for the browser login flow |
| `Helpers/ServerListHelper` | — | Polls `https://b2bf2.net/api/gamespy/servers` every 30s and caches the list the Search server hands back to the game |

`GameSpyHelper.GameSpyEncoding` is a byte-for-byte reimplementation of GameSpy's proprietary RC4-like stream
cipher (ported from decompiled/obfuscated reference code — variable names like `u0002`/`Two`/`Three` are
intentionally opaque, mirroring the original). Don't try to "clean up" the naming without a protocol
reference; the byte-level behavior is the entire point.

## Auth flow

`AccountInfo` (`B2BF.Common/Account/AccountInfo.cs`) implements an OAuth2 PKCE-ish flow against
`accounts.phoenixnetwork.net`:

1. `GetLoginUrl()` generates a code verifier/state and opens the browser to the authorize endpoint.
2. The browser redirects to `http://localhost:8888/oauthloginreturn`, caught by `HttpServer.ProcessMagma`,
   which hands the code/state to `AccountInfo.ValidateLoginResult`.
3. The resulting access token is persisted via `Settings.RememberMeContainer` and used both to call
   `b2bf2.net` APIs (server list, CD key) and to authenticate the in-game GameSpy CD-key handshake.

## Backend endpoints

Every Phoenix Network / B2BF2 hostname the app talks to is centralized in `B2BF.Common/Data/Endpoints.cs` -
don't reintroduce hardcoded `accounts.phoenixnetwork.net`/`b2bf2.net`/`cdn.phoenixnetwork.net` string
literals elsewhere. As of 2026-07 the OAuth login flow and the `b2bf2.net` API (server list, CD key, stats
proxy) are known broken: `accounts.phoenixnetwork.net` was rebuilt as a client-side SPA and no longer
exposes the old `/oauth/token` / `/oauth/user` server endpoints, and `b2bf2.net` does not resolve at all.
`cdn.phoenixnetwork.net` (game + launcher update manifests) is still live and correct. `HttpServer` now
parses the OAuth callback with a real query-string parser instead of hardcoded offsets, and swallowed
exceptions across the login/update path now report to Sentry instead of disappearing silently - if you're
chasing another "it just doesn't work" report, check Sentry/logs first rather than assuming another silent
failure needs to be found by inspection.

## Settings persistence

`B2BF.Common/Data/Settings.cs` is a hand-rolled XML key/value store at
`%MyDocuments%\B2BF\settings.xml` (read via XPath, written via `XmlDocument`) — there's no config framework
here, just `ReadValue`/`WriteValue`. `Settings.BF2GamePath` derives the actual game folder from
`GamePath` (it may point at the game root or a `Battlefield2` subfolder depending on install layout).

## Update flow

`OldPhoenixUpdater` (`B2BF.Common/Updater/OldPhoenixUpdater.cs`) drives the game-file updater: it fetches a
JSON manifest (`PhoenixUpdateXml`, despite the name, no XML involved) from
`cdn.phoenixnetwork.net/updater/game-bf2.json`, compares against the local `version.txt`, and downloads
missing/mismatched files (verified via HMACMD5 keyed by filename) from
`cdn.phoenixnetwork.net/updater/versions/client/Battlefield2/{version}/`. The launcher itself
self-updates separately via `AutoUpdater.NET` against `client-launcher.xml`.

Game launch (`Form1.button1_Click`) does a few notable things beyond just starting `BF2.exe`:
- Kills any running `bf2.exe` first (prompting the user).
- Binary-patches a fixed offset (`0x5627E0`) in `BF2.exe` to point at `WS2_32.dll` (bf2hub-style patch) —
  this offset is BF2-executable-version-specific.
- Ensures a BF2 profile exists via `ProfileHelper.CreateProfileIfNotExists()`, which writes `Profile.con`
  and a hardcoded default `Controls.con` if the account has no existing GameSpy-nick-matching profile.
- Disables BF2Hub's own auto-patcher via `RegistryHelper.DisableBF2HubAutoPatching()` so it doesn't fight
  with this launcher's patch/update.

## Error reporting

Both `B2BF.Launcher` and `B2BF.Common` report unhandled exceptions to Sentry (DSN hardcoded in
`Program.cs`/call sites). Keep that in mind if adding new top-level exception handling — prefer letting
exceptions surface to the existing Sentry hooks over swallowing them, except where the codebase already
intentionally swallows expected failures (e.g. registry access on non-admin, best-effort file cleanup).
