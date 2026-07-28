package com.itau.sg2.custodiaposvenda.infrastructure.adapters.outbound;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.firehose")
public class FirehoseProperties {

    private String deliveryStreamName;
    private String auditoriaDeliveryStreamName;

    public String getDeliveryStreamName() { return deliveryStreamName; }

    public void setDeliveryStreamName(String deliveryStreamName) { this.deliveryStreamName = deliveryStreamName; }

    public String getAuditoriaDeliveryStreamName() { return auditoriaDeliveryStreamName; }

    public void setAuditoriaDeliveryStreamName(String auditoriaDeliveryStreamName) {
        this.auditoriaDeliveryStreamName = auditoriaDeliveryStreamName;
    }
}
