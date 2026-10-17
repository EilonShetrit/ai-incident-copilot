FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The base image ships a Yarn apt source whose signing key has expired, which breaks
# apt-get update in the Docker-in-Docker feature. This project does not use Yarn.
RUN rm -f /etc/apt/sources.list.d/yarn.list
