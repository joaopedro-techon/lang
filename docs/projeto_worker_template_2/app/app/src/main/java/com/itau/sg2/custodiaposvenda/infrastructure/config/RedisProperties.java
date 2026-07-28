package com.itau.sg2.custodiaposvenda.infrastructure.config;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "spring.data.redis")
public class RedisProperties {

    private String host;
    private String replicaHost;
    private int port;
    private String password;
    private Ssl ssl = new Ssl();
    private Lettuce lettuce = new Lettuce();

    public String getHost() { return host; }

    public void setHost(String host) { this.host = host; }

    public String getReplicaHost() { return replicaHost; }

    public void setReplicaHost(String replicaHost) { this.replicaHost = replicaHost; }

    public int getPort() { return port; }

    public void setPort(int port) { this.port = port; }

    public String getPassword() { return password; }

    public void setPassword(String password) { this.password = password; }

    public Ssl getSsl() { return ssl; }

    public void setSsl(Ssl ssl) { this.ssl = ssl; }

    public Lettuce getLettuce() { return lettuce; }

    public void setLettuce(Lettuce lettuce) { this.lettuce = lettuce; }

    public static class Ssl {
        private boolean enabled;

        public boolean isEnabled() { return enabled; }

        public void setEnabled(boolean enabled) { this.enabled = enabled; }
    }

    public static class Lettuce {
        private Pool pool = new Pool();

        public Pool getPool() { return pool; }

        public void setPool(Pool pool) { this.pool = pool; }

        public static class Pool {
            private int maxActive;
            private int maxIdle;
            private int minIdle;

            public int getMaxActive() { return maxActive; }

            public void setMaxActive(int maxActive) { this.maxActive = maxActive; }

            public int getMaxIdle() { return maxIdle; }

            public void setMaxIdle(int maxIdle) { this.maxIdle = maxIdle; }

            public int getMinIdle() { return minIdle; }

            public void setMinIdle(int minIdle) { this.minIdle = minIdle; }
        }
    }
}
