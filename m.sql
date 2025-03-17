-- Creating temporary table for classification_df
CREATE TEMP TABLE classification_df AS
SELECT *
FROM SP_Classification
WHERE DATE(outUTC) = CURRENT_DATE
  AND DATE(inUTC) = CURRENT_DATE;

-- Creating temporary table for exclude_classification_df
CREATE TEMP TABLE exclude_classification_df AS
SELECT assetId AS exclude_assetId
FROM classification_df
WHERE classificationId = 591;

-- Creating temporary table for deployments_df
CREATE TEMP TABLE deployments_df AS
SELECT *
FROM SP_Deployment
WHERE environment = 'Production'
  AND status = 'Decommissioned';

-- Creating temporary table for deployments_filtered
CREATE TEMP TABLE deployments_filtered AS
SELECT d.*
FROM deployments_df d
LEFT JOIN exclude_classification_df e
ON d.deploymentId = e.exclude_assetId
WHERE e.exclude_assetId IS NULL;

-- Creating temporary table for classification_bcp
CREATE TEMP TABLE classification_bcp AS
SELECT DISTINCT assetId, classificationId
FROM classification_df
WHERE classificationId IN (114, 115, 116, 117);

-- Creating final temporary table dep_classification_bcp
CREATE TEMP TABLE dep_classification_bcp AS
SELECT d.*, c.classificationId,
    CASE 
        WHEN c.classificationId = 114 THEN 'tierA'
        WHEN c.classificationId = 115 THEN 'tierBAsia'
        WHEN c.classificationId = 116 AND d.rto IN (1,2) THEN 'tierBNonAsia'
        WHEN c.classificationId = 117 AND d.rto IN (1,2) THEN 'tierC'
        ELSE 'InvalidTier'
    END AS checkBcpTier
FROM deployments_filtered d
LEFT JOIN classification_bcp c
ON d.deploymentId = c.assetId;


============================================================



-- Create temporary table for databases
CREATE TEMPORARY TABLE databases AS 
SELECT DISTINCT deploymentId AS db_deploymentId
FROM SP_Databases
WHERE ownershipType = 'DependencyOnly'
AND entityTypeName LIKE '%MONGODB%';

-- Create temporary table for host_df
CREATE TEMPORARY TABLE host_df AS 
SELECT DISTINCT deploymentId AS host_deployment_id
FROM SP_Host
WHERE ownership = 'DependencyOnly'
AND type = 'Database';

-- Create temporary table for classification_public_cloud
CREATE TEMPORARY TABLE classification_public_cloud AS 
SELECT DISTINCT assetId AS assetId_pub
FROM classification_df
WHERE appdirType = 'PubCloud' AND appdirValue = 'Yes';

-- Create temporary table for assets_for_ctfc
CREATE TEMPORARY TABLE assets_for_ctfc AS 
SELECT DISTINCT assetId AS assetId_swap
FROM classification_df
WHERE ClassificationName = 'Swap Dealer application';

-- Create temporary table for assets_for_ibs_integral
CREATE TEMPORARY TABLE assets_for_ibs_integral AS 
SELECT DISTINCT assetId AS assetId_ibs
FROM classification_df
WHERE ClassificationId = '2962';

CREATE TABLE stateful_data_platform AS 
SELECT DISTINCT assetId AS assetId_sdp 
FROM classification_df 
WHERE classificationId = '3523'


=============================================================================
