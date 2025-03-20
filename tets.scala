val getTopLevelParent = catalog_relationship
  .select(
    col("first_resource_id").alias("destination"),
    lit(null).cast("string").alias("source"),  // Ensure source has same data type
    col("first_resource_id").alias("root")
  )
  .join(secondResourceIds, col("destination") === col("second_resource_id"), "left_anti") 

// Step 2: Recursive-like join to establish hierarchy
val secondResourceDF = catalog_relationship.alias("al")
  .join(getTopLevelParent.alias("gtlp"), col("gtlp.destination") === col("al.first_resource_id"))
  .select(
    col("al.second_resource_id").alias("destination"),
    col("al.first_resource_id").alias("source"),
    col("gtlp.root")
  )

// Step 3: Combine both results
val finalResult = getTopLevelParent.union(secondResourceDF)
