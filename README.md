# Normal OJ

## Clone this project

```bash
git clone https://github.com/Normal-OJ/Normal-OJ.git
```
Enter the project directory:
```bash
cd Normal-OJ
```
Clone submodules:
```bash
git submodule update --init --recursive
git submodule foreach --recursive git checkout main
```

## Overview of the project
Checkout the [Introduction](https://github.com/Normal-OJ).

NOJ contains three parts:
1. **Backend**: Python web server, provides RESTful API, communicates with the database and the sandbox.
2. **Frontend**: The user interface that interacts with the backend, written in Vue.js.
3. **Sandbox**: Takes the user's submission, compiles and executes the code, and returns the result to the backend.

Each subfolder in this project corresponds to a specific part of NOJ (Backend, Frontend, Sandbox) and includes its own package manager, such as `pnpm` or `poetry`. Ideally, each part could be developed separately and locally, please refer to the `README.md` file in each subfolder.

To run the entire project, see the "Run Docker" section below.

## Run Docker

#### Build images and start

`docker-compose up -d`

or if you want to rebuild the images

`docker-compose up --build -d`

When you run `docker-compose up`, Docker Compose automatically combines `docker-compose.yml` and `docker-compose.override.yml`. You can check the `docker-compose.override.yml` file, and you'll see the frontend is running locally on port 8080.

In production, the frontend is hosted on Cloudflare Pages, not locally.

#### Other commands

- `docker-compose start`
- `docker-compose restart [service]`
- `docker-compose stop`
- `docker-compose down`

## Setup Sandbox

### Sandbox

1. in `Sandbox/.config/submission.json`:
  - set `working_dir` to your desired location to store the user's submission
2. cd to `Sandbox` folder, run `./build.sh`, this will build the images you need to compile and execute user's submission
3. that's all :P, i think
