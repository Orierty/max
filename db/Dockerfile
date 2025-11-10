FROM postgres:15

# Устанавливаем локаль (опционально)
ENV LANG en_US.utf8

# Копируем SQL схему в контейнер
COPY schema.sql /docker-entrypoint-initdb.d/1_schema.sql
COPY init-db.sh /docker-entrypoint-initdb.d/0_init-db.sh

# Делаем их исполняемыми
RUN chmod +x /docker-entrypoint-initdb.d/0_init-db.sh

# entrypoint ["/docker-entrypoint-initdb.d/0_init-db.sh"]