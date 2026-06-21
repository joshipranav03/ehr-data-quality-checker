# Deploy to Hugging Face Spaces

Spaces is a great free home for this demo — it runs Docker apps for free and is
where the data/health-tech community already looks.

## One-time setup

1. Create a new Space: <https://huggingface.co/new-space>
   - **SDK:** Docker → *Blank*
   - **Hardware:** CPU basic (free)
2. The Space is a git repo. Push this project into it. The only Space-specific
   requirement is that the **Space's root `README.md` carries the YAML
   frontmatter** in [`deploy/huggingface/README.md`](README.md) — it tells
   Spaces to build the Docker image and route traffic to `app_port: 8000`
   (the port our `Dockerfile` listens on by default).

```bash
# from a clone of this project
git remote add space https://huggingface.co/spaces/joshipranav03/ehr-data-quality-checker

# use the Space card as the repo README (keep your GitHub README elsewhere if you like)
cp deploy/huggingface/README.md README.space.md
# then, on the branch you push to the Space, make README.md = the Space card:
#   git mv README.md README.github.md && git mv README.space.md README.md   (optional)

git push space main
```

Spaces builds the `Dockerfile` automatically and serves the app. Build logs and
the live URL appear on the Space page.

## Notes
- **Port:** Spaces routes to `app_port` from the frontmatter (`8000`). Our
  `Dockerfile` defaults `PORT=8000`, so no change is needed.
- **Persistence:** leave `EHR_HISTORY=off` (the default for ephemeral hosts) —
  Spaces storage is not durable. Set it under the Space's *Settings → Variables*
  only if you attach persistent storage.
- **No PHI:** the bundled data is synthetic. Don't upload real patient data to a
  public Space.
