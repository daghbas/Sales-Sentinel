# Deployment Status

The complete unpacked source is on `main`. GitHub Actions is responsible for downloading the licensed Redsea daily source, verifying its published hashes, rebuilding SQLite and the selected model, running migrations and tests, starting the live Flask application, and committing Chromium screenshots. Vercel deployment remains pending until the connected Vercel plugin is available or the repository is imported into an active Vercel project.
