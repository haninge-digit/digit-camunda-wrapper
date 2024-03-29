FROM python:3.9-slim

WORKDIR /usr/src/app
ENV TZ="Europe/Stockholm"

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD [ "python", "./main.py" ]
