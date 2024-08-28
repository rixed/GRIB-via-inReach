.PHONY: all run docker docker-srv docker-clt docker-push

all: build

check:
	mypy --install-types *.py

build: docker docker-srv docker-clt

.mail-conf.json:
	@echo The file $@ must be created with your own imap/smtp settings
	@echo (see mail2grib.py to figure out the format)

docker: docker-srv docker-clt

docker-srv: Dockerfile-srv start mail2grib.py codec.py requirements.txt .mail-conf.json
	@echo Building SERVER docker image
	docker build -t rixed/grib-via-inreach -f $< .

docker-clt: Dockerfile-clt decode.py codec.py eccodes.patch
	@echo Building CLIENT docker image
	docker build -t rixed/grib-via-inreach-clt -f $< .

docker-push:
	@echo Pushing docker images
	docker push rixed/grib-via-inreach-clt
	docker push rixed/grib-via-inreach

run:
	docker rm -f vaudoomap || true
	docker run --name vaudoomap --restart=unless-stopped -d rixed/grib-via-inreach bash
