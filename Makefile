.PHONY: all run docker docker-srv docker-clt docker-push

all: docker docker-srv docker-clt

.mail-conf.json:
	@echo The file $@ must be created with your own imap/smtp settings
	@echo (see mail2grib.py to figure out the format)

docker: docker-srv docker-clt

docker-srv: Dockerfile-srv
	@echo Building SERVER docker image
	docker build -t rixed/grib-via-inreach -f $< .

docker-clt: Dockerfile-clt
	@echo Building CLIENT docker image
	docker build -t rixed/grib-via-inreach-clt -f $< .

docker-push:
	@echo Pushing docker images
	docker push rixed/grib-via-inreach-clt
	docker push rixed/grib-via-inreach

run:
	docker run --name vaudoomap -d rixed/grib-via-inreach bash
