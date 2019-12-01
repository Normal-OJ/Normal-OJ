# Normal OJ

## How to

1. `git clone --recurse-submodules https://github.com/Normal-OJ/Normal-OJ.git`
2. `cd Normal-OJ`
3. `git submodule foreach --recursive git checkout master`

### Push

For example, if you want to push `Normal-OJ/Back-End`:

1. `cd Back-End`
2. `git push`

### Pull

Pull all:

`git submodule foreach --recursive git pull`

## Run Docker

#### Build images and start

`docker-compose up -d`

or if you want to rebuild the images

`docker-compose up --build -d`

#### Start

`docker-compose start`

#### Restart

`docker-compose restart [service]`

#### Stop

`docker-compose stop`

#### Down

`docker-compose down`
