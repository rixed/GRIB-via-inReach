.PHONY: all docker run

all: docker docker-srv docker-clt

include make.inc

docker: docker-srv docker-clt

docker-srv: Dockerfile-srv
	@echo Building SERVER docker image
	docker build -t rixed/grib-via-inreach -f $< --build-arg EMAIL=$(EMAIL) .

docker-clt: Dockerfile-clt
	@echo Building CLIENT docker image
	docker build -t rixed/grib-via-inreach -f $< --build-arg EMAIL=$(EMAIL) .

run:
	docker run -e 'YOUR_EMAIL=$(EMAIL)' --name vaudoomap -d rixed/grib-via-inreach bash
