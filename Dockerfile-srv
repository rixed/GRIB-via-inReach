ARG EMAIL
FROM debian:stable

RUN cd / && \
    echo 'APT::Install-Recommends "0";' > \
      /etc/apt/apt.conf.d/no_recommends && \
    echo 'APT::Get::AutomaticRemove "1";' >> \
      /etc/apt/apt.conf.d/no_recommends && \
    DEBIAN_FRONTEND=noninteractive \
      apt-get --yes update && \
    DEBIAN_FRONTEND=noninteractive \
      apt-get --yes upgrade && \
    DEBIAN_FRONTEND=noninteractive \
      apt-get --yes install \
        dpkg-dev \
        python3 \
        python3-cfgrib \
        python3-googleapi \
        python3-google-auth-oauthlib \
        python3-numpy \
        python3-pandas

COPY start main.py emailfunctions.py codec.py credentials.json /GRIB-via-inReach/
# A patch to fix findlibs
COPY eccodes.patch /tmp
RUN patch /usr/lib/python3/dist-packages/gribapi/bindings.py /tmp/eccodes.patch

ENV LIST_OF_PREVIOUS_MESSAGES_FILE_LOCATION=/GRIB-via-inReach/prev_files
ENV YOUR_EMAIL=${EMAIL}
ENV TOKEN_PATH=/GRIB-via-inReach/.token
ENV CREDENTIALS_PATH=/GRIB-via-inReach/credentials.json
ENV ATTACHMENTS_PATH=/GRIB-via-inReach/attachments

WORKDIR /GRIB-via-inReach
LABEL maintainer="rixed@happyleptic.org"
ENTRYPOINT ["/GRIB-via-inReach/start"]
