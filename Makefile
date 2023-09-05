.PHONY: all docker run

all: docker

include make.inc

docker: Dockerfile
	docker build -t rixed/grib-via-inreach -f Dockerfile --build-arg EMAIL=$(EMAIL) .

run:
	docker run -e 'YOUR_EMAIL=$(EMAIL)' --name vaudoomap -d rixed/grib-via-inreach bash
