package com.csnd.test.controller;

import com.alibaba.fastjson.JSON;
import com.csnd.test.entity.*;
import com.csnd.test.service.TestReportApplication;
import lombok.extern.slf4j.Slf4j;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/report")
@Slf4j
public class TestReportController {

    private static final Logger logger = LoggerFactory.getLogger(TestReportController.class);


    @Resource
    TestReportApplication testReportApplication;


    @RequestMapping("/test1")
    @ResponseBody
    public Result test1() throws InterruptedException {
        String url = "https://decision-net-server.aios-test.com/DecisionNetService/tryRunDecisionNet";
        List<String> param = new ArrayList<>();
        param.add("{\"applicationId\":\"0\",\"async\":0,\"netId\":\"16149869976616960\",\"inputs\":\"[{\\\"name\\\":\\\"INPUT\\\",\\\"type\\\":\\\"String\\\",\\\"value\\\":{\\\"type\\\":2,\\\"literal\\\":\\\"INPUT\\\"}}]\"}");

        Map<String,String> map = new HashMap<>();
        map.put("Host","decision-net-server.aios-test.com");
        map.put("Accept","application/json; charset=UTF-8");
        map.put("Content-Type","application/json; charset=UTF-8");
        map.put("Cookie","XingheToken=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWFsbSI6IjEyNDE2MzA1NzM2OTc0MzM2IiwiZXhwIjoxNzYxNzAwMDc3LjA3MzYsInJlYWxtTmFtZSI6IlRlc3RUZW5hbnRBIiwicm9sZXMiOlsiMTI0MTYzMDU3MzczNjc1NTIiLCIxMjQxNjMwNTczNzM2NzU1MyIsIjEyNDQ5MzE0NTc0OTU4NTkyIiwiMTI0MTYzNDk5NzgzNjE4NTYiLCIxMzYzOTQ5OTU2NzU5NTUyMCJdLCJ1c2VybmFtZSI6InlhbnNsIiwic2Vzc2lvbklkIjoiQTczQzE4MTYxMDAyMjA5RjBEQjlEMUQxQjkxRjFEMjgiLCJ1c2VySWQiOiIxNDM2MDUyMjQyMDc4MTA1NiJ9.Nr2FikG39JBTQ9jCU2nV4-zZ_6-2bHA0l1XwH5pi86E");

        String header = JSON.toJSONString(map);
        return executeSyncReport(url, header, param);
    }

    @PostMapping("/test")
    @ResponseBody
    public Result testReport() throws InterruptedException {

        String url = "https://decision-net-server.aios-test.com/DecisionNetService/tryRunDecisionNet";
        List<String> param = new ArrayList<>();
        param.add("{\"applicationId\":\"0\",\"async\":0,\"netId\":\"16149869976616960\",\"inputs\":\"[{\\\"name\\\":\\\"INPUT\\\",\\\"type\\\":\\\"String\\\",\\\"value\\\":{\\\"type\\\":2,\\\"literal\\\":\\\"INPUT\\\"}}]\"}");


        Map<String,String> map = new HashMap<>();
        map.put("Host","decision-net-server.aios-test.com");
        map.put("Accept","application/json; charset=UTF-8");
        map.put("Content-Type","application/json; charset=UTF-8");
        map.put("Cookie","XingheToken=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyZWFsbSI6IjEyNDE2MzA1NzM2OTc0MzM2IiwiZXhwIjoxNzYxNzAwMDc3LjA3MzYsInJlYWxtTmFtZSI6IlRlc3RUZW5hbnRBIiwicm9sZXMiOlsiMTI0MTYzMDU3MzczNjc1NTIiLCIxMjQxNjMwNTczNzM2NzU1MyIsIjEyNDQ5MzE0NTc0OTU4NTkyIiwiMTI0MTYzNDk5NzgzNjE4NTYiLCIxMzYzOTQ5OTU2NzU5NTUyMCJdLCJ1c2VybmFtZSI6InlhbnNsIiwic2Vzc2lvbklkIjoiQTczQzE4MTYxMDAyMjA5RjBEQjlEMUQxQjkxRjFEMjgiLCJ1c2VySWQiOiIxNDM2MDUyMjQyMDc4MTA1NiJ9.Nr2FikG39JBTQ9jCU2nV4-zZ_6-2bHA0l1XwH5pi86E");

        String header = JSON.toJSONString(map);
        return executeSyncReport(url, header, param);
    }


    @PostMapping("/generatAutotestReport")
    @ResponseBody
    public Result chatHistory(@RequestBody ReportGenerateRequest reportGenerateRequest) throws InterruptedException {


        String url = reportGenerateRequest.getUrl();
        String header = reportGenerateRequest.getHeader();
        List<String> param = reportGenerateRequest.getParam();

        return executeSyncReport(url, header, param);
    }

    private Result executeSyncReport(String url, String header, List<String> param) throws InterruptedException {
        logger.info("header is {}", header);

        try {
            String result = testReportApplication.generatReport(url, header, param).get();
            if (result == null) {
                logger.error("生成报告失败，有接口结果为空");
                throw new IllegalStateException("生成报告失败,请联系管理员");
            }

            logger.info("生成报告结果 is：{}", result);
            return new Result().ok(result);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            logger.error("生成报告被中断", e);
            throw e;
        } catch (Exception e) {
            logger.error("生成报告失败", e);
            throw new RuntimeException("生成报告失败,请联系管理员", e);
        }
    }


}
