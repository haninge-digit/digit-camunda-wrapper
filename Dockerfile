FROM python:3.9-slim

WORKDIR /usr/src/app
ENV TZ="Europe/Stockholm"

RUN pip install -U pip wheel setuptools
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD [ "python", "./main.py" ]