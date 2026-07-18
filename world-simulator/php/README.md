# Concert of Nations — PHP edition

A full port of the Python `worldsim` game to plain PHP, for hosts (like
typical cPanel shared hosting) that have no shell/SSH access, no Python
runtime, and no ability to run a custom long-lived server process.

No external dependencies, no Composer, no build step. Requires PHP 7.4+
(tested against PHP 8.4) with the default session extension enabled, which
virtually every shared host has.

## Deploying to cPanel

1. Upload the entire contents of this `php/` directory into `public_html`
   (or a subdirectory like `public_html/game` if you want it at a sub-path)
   using the cPanel File Manager or FTP/SFTP.
2. That's it — no `.htaccess`, no rewrite rules, no cron jobs, no database.
   Visit `index.php` (e.g. `https://yourdomain.com/game/index.php`) in a
   browser.
3. PHP sessions are used to store each player's in-progress game
   (`$_SESSION`), so the host's default session save path just needs to be
   writable, which is the default on virtually all shared hosting.

## Files

- `models.php` — Nation/World data structures and helpers
- `orders.php` — order types, validation, and resolution logic
- `ai.php` — deterministic AI scoring for non-player nations (no LLM/ML)
- `engine.php` — turn loop, passive effects, elections, wars, markets
- `scenarios.php` — the 28-nation starting world
- `parser.php` — free-text command parser with the actor-lock guarantee
- `api.php` — JSON API entry point (`api.php?action=...`)
- `index.php` — the game's HTML/CSS/JS frontend

## Notes

- This is a faithful port of the Python version in `../worldsim/`, including
  every game-balance fix from that codebase's history (peace-offer dominance
  check, military build cap, deterministic conquest tie-breaks, unrest-gated
  minor events, and the actor-lock parsing guarantee).
- Unlike the Python CLI, there is no seeded/reproducible RNG — each PHP
  process is a fresh web request from a real player, so `mt_rand()` is used
  directly.
