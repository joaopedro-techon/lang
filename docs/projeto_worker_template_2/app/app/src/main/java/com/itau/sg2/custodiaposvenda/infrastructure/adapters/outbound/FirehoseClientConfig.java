package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.http.crt.AwsCrtAsyncHttpClient;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.firehose.FirehoseAsyncClient;

@Configuration
public class FirehoseClientConfig {

    @Bean
    public FirehoseAsyncClient firehoseAsyncClient(@Value("${spring.cloud.aws.region.static}") String region) {
        return FirehoseAsyncClient.builder()
                .region(Region.of(region))
                .httpClient(AwsCrtAsyncHttpClient.create())
                .build();
    }
}
