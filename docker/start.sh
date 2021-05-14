#!/bin/bash

CA_BUNDLE_PATH=$(python3 -m certifi)

CERT_PATH=${CERT_PATH:-"/trusted_certs"}

if [ ! -d "${CERT_PATH}" ]; then
   echo "${CERT_PATH} does not exist. Nothing to do..."
else
  cd "${CERT_PATH}"

  for cert in `ls *.pem`; do
    md5res=`md5sum $cert`
    md5sum_str=`echo "$md5res" | cut -d' ' -f1`
    grep "$md5sum_str" .added_certs &> /dev/null
    if [ $? == 0 ]; then
          echo "Cert $cert alredy added"
    else
       echo "Adding Cert from file $cert to the CA bundle"
       cat $cert >> "$CA_BUNDLE_PATH" && echo "$md5res" >> .added_certs
    fi
  done

  cd -
fi  


if [ "${ENABLE_HTTPS}" == "True" ]; then
  if test -e /certs/cert.pem && test -f /certs/key.pem ; then
    exec gunicorn --bind 0.0.0.0:5001 -w "$WORKERS" --certfile /certs/cert.pem --keyfile /certs/key.pem --timeout "$TIMEOUT"  orchdashboard:app
  else
    echo "[ERROR] File /certs/cert.pem or /certs/key.pem NOT FOUND!"
    exit 1
  fi
else
  exec gunicorn --bind 0.0.0.0:5001 -w "$WORKERS" --timeout "$TIMEOUT"  orchdashboard:app
fi
