.PHONY: all docker

all: docker

include make.inc

docker: Dockerfile
	docker build -t rixed/grib-via-inreach -f Dockerfile --build-arg EMAIL=$(EMAIL) .
