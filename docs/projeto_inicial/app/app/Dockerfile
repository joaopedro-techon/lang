FROM docker-remotes.artifactory.prod.aws.cloud.ihf/alpine:latest
RUN apk --update add openjdk11

RUN mkdir /app
ADD app/*.jar /app/app.jar

EXPOSE 2000

ENTRYPOINT ["java", "-Djava.security.egd=file:/dev/./urandom", "-jar", "/app/app.jar"]
