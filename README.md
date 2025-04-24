# Normal OJ

## Clone this project

1. `git clone --recurse-submodules https://github.com/Normal-OJ/Normal-OJ.git`
2. `cd Normal-OJ`
3. `git submodule foreach --recursive git checkout main`

## Overview of the project

NOJ consists of three parts:
1. **[Backend](https://github.com/Normal-OJ/Back-End)**: Python web server, provides RESTful API, communicates with the database and the sandbox.
2. **[Frontend](https://github.com/Normal-OJ/new-front-end)**: The user interface that interacts with the backend, written in Vue.js.
3. **[Sandbox](https://github.com/Normal-OJ/Sandbox)**: Takes the user's submission, compiles and executes the code, and returns the result to the backend.

Each subfolder in this project corresponds to a specific part of NOJ (Backend, Frontend, Sandbox) and includes its own package manager, such as `pnpm` or `poetry`. Ideally, each part could be developed separately and locally, please refer to the `README.md` file in each subfolder.

You may also be interested in this [Introduction](https://github.com/Normal-OJ).

## Build and Run the entire project

### Setup Sandbox

1. Make sure you have Docker installed and running.
2. cd to `Sandbox` folder, run `./build.sh`, this will build the images you need to compile and execute user's submission.
3. Replace `working_dir` in `Sandbox/.config/submission.json` as stated in the logs of the previous step.
  - Recommend to use `/path/to/Normal-OJ/Sandbox/submissions`.
  - This directory is for storing the user's submission.

### Run Docker

#### Build images and start

`docker compose up -d`

or if you want to rebuild the images

`docker compose up --build -d`

When you run `docker compose up`, Docker Compose automatically combines `docker compose.yml` and `docker compose.override.yml`. You can check the `docker compose.override.yml` file, and you'll see the frontend is running locally on port 8080.

In production, the frontend is hosted on Cloudflare Pages, not locally.

#### Other commands

- `docker compose start`
- `docker compose restart [service]`
- `docker compose stop`
- `docker compose down`
