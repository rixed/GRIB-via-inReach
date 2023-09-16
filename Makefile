.PHONY: all run docker docker-srv docker-clt docker-push

all: docker docker-srv docker-clt

include make.inc

docker: docker-srv docker-clt

docker-srv: Dockerfile-srv
	@echo Building SERVER docker image
	docker build -t rixed/grib-via-inreach -f $< --build-arg EMAIL=$(EMAIL) .

docker-clt: Dockerfile-clt
	@echo Building CLIENT docker image
	docker build -t rixed/grib-via-inreach-clt -f $< --build-arg EMAIL=$(EMAIL) .

docker-push:
	@echo Pushing docker images
	docker push rixed/grib-via-inreach-clt
	docker push rixed/grib-via-inreach

run:
	docker run -e 'YOUR_EMAIL=$(EMAIL)' --name vaudoomap -d rixed/grib-via-inreach bash
